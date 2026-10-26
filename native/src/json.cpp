// SPDX-License-Identifier: GPL-3.0-or-later
#include "quickshare/json.h"
#include <climits>
#include <cctype>

namespace quickshare {
namespace {
void need(bool ok) { if(!ok) throw Error("Invalid worker JSON"); }
void appendUtf8(std::string &out, unsigned n) {
    if(n<128) out+=char(n);
    else if(n<2048) { out+=char(0xc0|(n>>6)); out+=char(0x80|(n&63)); }
    else if(n<65536) { out+=char(0xe0|(n>>12)); out+=char(0x80|((n>>6)&63)); out+=char(0x80|(n&63)); }
    else { out+=char(0xf0|(n>>18)); out+=char(0x80|((n>>12)&63)); out+=char(0x80|((n>>6)&63)); out+=char(0x80|(n&63)); }
}
class Parser {
    const std::string &s; std::size_t p=0; unsigned nodes=0;
    void space() { while(p<s.size() && (s[p]==' ' || s[p]=='\r' || s[p]=='\n' || s[p]=='\t')) ++p; }
    char take() { need(p<s.size()); return s[p++]; }
    unsigned hex4() {
        unsigned value=0;
        for(int i=0;i<4;++i) { char c=take(); unsigned n;
            if(c>='0'&&c<='9') n=c-'0'; else if(c>='a'&&c<='f') n=c-'a'+10; else { need(c>='A'&&c<='F'); n=c-'A'+10; }
            value=value*16+n;
        } return value;
    }
    std::string string() {
        need(take()=='"'); std::string out;
        while(true) {
            unsigned char c=take(); if(c=='"') break; need(c>=32);
            if(c!='\\') { out+=char(c); continue; }
            char e=take();
            switch(e) {
            case '"': case '\\': case '/': out+=e; break;
            case 'b': out+='\b'; break; case 'f': out+='\f'; break;
            case 'n': out+='\n'; break; case 'r': out+='\r'; break; case 't': out+='\t'; break;
            case 'u': {
                unsigned cp=hex4();
                if(cp>=0xd800 && cp<=0xdbff) { need(take()=='\\' && take()=='u'); unsigned low=hex4(); need(low>=0xdc00 && low<=0xdfff); cp=0x10000+((cp-0xd800)<<10)+(low-0xdc00); }
                else need(cp<0xdc00 || cp>0xdfff);
                appendUtf8(out,cp); break;
            }
            default: need(false);
            }
        }
        need(validUtf8(out)); return out;
    }
    Json value(unsigned depth) {
        need(depth<=16 && ++nodes<=2048); space(); need(p<s.size()); Json out;
        if(s[p]=='"') { out.kind=Json::String; out.text=string(); return out; }
        if(s[p]=='{' || s[p]=='[') {
            char close=take()=='{' ? '}' : ']'; out.kind=close=='}' ? Json::Object : Json::Array;
            space(); if(p<s.size() && s[p]==close) { ++p; return out; }
            while(true) {
                space();
                if(out.kind==Json::Object) {
                    auto key=string(); space(); need(take()==':'); auto child=value(depth+1);
                    need(out.object.emplace(std::move(key),std::move(child)).second);
                } else out.array.push_back(value(depth+1));
                space(); char separator=take(); if(separator==close) break; need(separator==',');
            }
            return out;
        }
        for(auto literal: {"true","false","null"}) {
            std::string word=literal;
            if(s.compare(p,word.size(),word)==0) { p+=word.size(); out.kind=word=="null" ? Json::Null : Json::Boolean; out.boolean=word=="true"; return out; }
        }
        out.kind=Json::Number; bool negative=false;
        if(s[p]=='-') { negative=true; ++p; }
        need(p<s.size() && s[p]>='0' && s[p]<='9');
        std::size_t start=p; std::uint64_t magnitude=0, limit=std::uint64_t(INT64_MAX)+(negative?1:0);
        while(p<s.size() && s[p]>='0' && s[p]<='9') {
            unsigned digit=s[p++]-'0'; need(magnitude<=(limit-digit)/10); magnitude=magnitude*10+digit;
        }
        need(p-start==1 || s[start]!='0');
        out.number=negative ? (magnitude==std::uint64_t(INT64_MAX)+1 ? INT64_MIN : -std::int64_t(magnitude)) : std::int64_t(magnitude);
        return out;
    }
public:
    explicit Parser(const std::string &input):s(input) {}
    Json parse() { need(s.size()<=65536); auto out=value(0); space(); need(p==s.size()); return out; }
};
}
bool validUtf8(const std::string &s) {
    for(std::size_t p=0;p<s.size();) {
        unsigned a=static_cast<unsigned char>(s[p++]), count=0, value=0, minimum=0;
        if(a<128) continue;
        if(a>=0xc2 && a<=0xdf) { count=1; value=a&31; minimum=128; }
        else if(a>=0xe0 && a<=0xef) { count=2; value=a&15; minimum=2048; }
        else if(a>=0xf0 && a<=0xf4) { count=3; value=a&7; minimum=65536; } else return false;
        if(count>s.size()-p) return false;
        while(count--) { unsigned b=static_cast<unsigned char>(s[p++]); if((b&0xc0)!=0x80) return false; value=(value<<6)|(b&63); }
        if(value<minimum || value>0x10ffff || (value>=0xd800 && value<=0xdfff)) return false;
    } return true;
}
const Json &Json::at(const std::string &key) const { if(kind!=Object || !object.count(key)) throw Error("Missing worker configuration field"); return object.at(key); }
bool Json::has(const std::string &key) const { return kind==Object && object.count(key); }
std::string Json::string() const { if(kind!=String) throw Error("Expected JSON string"); return text; }
std::int64_t Json::integer() const { if(kind!=Number) throw Error("Expected JSON integer"); return number; }
bool Json::flag() const { if(kind!=Boolean) throw Error("Expected JSON boolean"); return boolean; }
Json parseJson(const std::string &s) { return Parser(s).parse(); }
std::string quoteJson(const std::string &s) {
    if(!validUtf8(s)) throw Error("Invalid UTF-8 output");
    static const char hex[]="0123456789abcdef"; std::string out="\"";
    for(unsigned char c:s) { if(c=='"'||c=='\\') { out+='\\'; out+=char(c); } else if(c<32) { out+="\\u00";out+=hex[c>>4];out+=hex[c&15]; } else out+=char(c); }
    return out+'"';
}
}
