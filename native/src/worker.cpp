// SPDX-License-Identifier: GPL-3.0-or-later
// LAN file transfer implementation of the pinned Google/Bada wire schemas.
#include "quickshare/core.h"
#include "quickshare/json.h"
#include <openssl/rand.h>
#include <algorithm>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <list>
#include <map>
#include <mutex>
#include <set>
#include <thread>
#include <unistd.h>
#include <arpa/inet.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/syscall.h>

using namespace quickshare;
namespace {
constexpr std::uint64_t MaxBytes=8ULL*1024*1024*1024;
using Clock=std::chrono::steady_clock;
using Time=Clock::time_point;
volatile std::sig_atomic_t signaled=0;
void signalHandler(int) { signaled=1; }
void need(bool value,const char *message) { if(!value) throw Error(message); }
struct Canceled : Error { Canceled():Error("Transfer canceled") {} };
struct Closed : Error { Closed():Error("Peer closed the connection") {} };
struct Fd {
    int value=-1;
    explicit Fd(int fd=-1):value(fd) {}
    ~Fd() { if(value>=0) ::close(value); }
    Fd(Fd &&other) noexcept:value(other.value) { other.value=-1; }
    Fd &operator=(Fd &&other) noexcept { if(this!=&other) { if(value>=0)::close(value);value=other.value;other.value=-1; }return *this; }
    Fd(const Fd&)=delete; Fd &operator=(const Fd&)=delete;
};
Bytes randomData(std::size_t count) { Bytes out(count);need(RAND_bytes(out.data(),int(count))==1,"Random generation failed");return out; }
std::string string(const Bytes &value) { return std::string(value.begin(),value.end()); }
std::string token() { static const char hex[]="0123456789abcdef";std::string out;for(auto c:randomData(16)){out+=hex[c>>4];out+=hex[c&15];}return out; }
std::uint64_t payloadId() { std::uint64_t n=0;for(auto c:randomData(8))n=(n<<8)|c;return (n&INT64_MAX) ? (n&INT64_MAX) : 1; }
std::mutex outputMutex;
std::string object(std::initializer_list<std::pair<std::string,std::string>> fields) {
    std::string out="{";for(const auto &field:fields){if(out.size()>1)out+=',';out+=quoteJson(field.first)+":"+field.second;}return out+"}";
}
void event(std::initializer_list<std::pair<std::string,std::string>> fields) {
    std::lock_guard<std::mutex> lock(outputMutex);std::cout<<object(fields)<<'\n';std::cout.flush();
}
std::uint64_t number(const wire::Fields &fields,unsigned field,std::uint64_t fallback=0) {
    return wire::has(fields,field) ? wire::one(fields,field,0).integer : fallback;
}
Bytes data(const wire::Fields &fields,unsigned field) { return wire::has(fields,field) ? wire::one(fields,field,2).data : Bytes(); }
Bytes add(Bytes a,const Bytes &b) { return wire::join(a,b); }
Bytes frame(unsigned type,unsigned field,const Bytes &body) {
    auto v1=wire::integer(1,type);if(field)v1=add(v1,wire::blob(field,body));
    return add(wire::integer(1,1),wire::blob(2,v1));
}
wire::Fields unwrap(const Bytes &value) {
    auto outer=wire::parse(value);need(wire::one(outer,1,0).integer==1,"Unsupported frame version");return wire::parse(wire::one(outer,2,2).data);
}
Bytes endpoint(const std::string &name) {
    need(validUtf8(name)&&!name.empty()&&name.size()<=128,"Invalid device name");
    Bytes out{0x24};out=add(out,randomData(16));out.push_back(static_cast<unsigned char>(name.size()));return add(out,bytes(name));
}
std::string senderName(const wire::Fields &request) {
    auto raw=data(request,6);
    if(raw.size()>=18 && !(raw[0]&16) && raw[17]<=raw.size()-18) {
        std::string name(raw.begin()+18,raw.begin()+18+raw[17]);
        if(validUtf8(name)&&!name.empty())return name;
    }
    return "Quick Share device";
}
Bytes connectionResponse() {
    auto response=add(wire::integer(1,0),wire::integer(3,1));
    response=add(response,wire::blob(4,wire::integer(1,1)));
    response=add(response,wire::integer(5,0));response=add(response,wire::integer(7,1));
    return frame(2,3,add(response,wire::integer(9,600000)));
}
Bytes connectionRequest(const std::string &name) {
    auto info=endpoint(name);std::string id=token().substr(0,4);
    auto request=add(wire::blob(1,bytes(id)),wire::blob(2,bytes(name)));
    request=add(request,wire::integer(4,0));request=add(request,wire::integer(5,5));request=add(request,wire::blob(6,info));
    request=add(request,wire::integer(8,10000));request=add(request,wire::integer(9,600000));
    auto device=add(add(wire::blob(1,bytes(id)),wire::integer(2,1)),wire::blob(4,info));
    return frame(1,2,add(request,wire::blob(12,device)));
}
unsigned validateResponse(const Bytes &value) {
    auto v1=unwrap(value);need(number(v1,1)==2,"Expected connection response");auto response=wire::parse(wire::one(v1,3,2).data);
    need((wire::has(response,3) ? number(response,3)==1 : wire::has(response,1)) && number(response,1)==0,"Peer rejected connection");
    return unsigned(number(response,7));
}
struct Context;
struct Connection {
    Fd socket;
    std::string id=token();
    std::atomic<bool> canceled{false},done{false},waiting{false};
    std::atomic<int> consent{-1};
    std::unique_ptr<Session> session;
    Context *context;
    Time deadline=Clock::now()+std::chrono::seconds(15);
    Time lastWrite=Clock::now();
    explicit Connection(int fd,Context *ctx):socket(fd),context(ctx) {}
    void cancel() { canceled=true;::shutdown(socket.value,SHUT_RDWR); }
    void check() const;
    void exact(unsigned char *target,std::size_t size,bool writing);
    Bytes read();
    void write(const Bytes &value);
    void secureWrite(const Bytes &value) { write(session->seal(value));lastWrite=Clock::now(); }
    Bytes secureRead() { return session->open(read()); }
    void sharing(const Bytes &value);
};
struct Context {
    std::atomic<bool> stop{false},finished{false};
    std::mutex mutex;
    std::map<std::string,std::shared_ptr<Connection>> connections;
    void cancelAll() {stop=true;std::lock_guard<std::mutex> lock(mutex);for(auto &item:connections)item.second->cancel();}
};
void Connection::check() const {
    if(canceled || context->stop || signaled)throw Canceled();
    need(Clock::now()<deadline,"Connection or transfer timed out");
}
void Connection::exact(unsigned char *buffer,std::size_t size,bool writing) {
    Time inactive=Clock::now()+std::chrono::seconds(65);
    while(size) {
        check();need(Clock::now()<inactive,"Peer stopped responding");
        pollfd item{socket.value,short(writing?POLLOUT:POLLIN),0};int result=::poll(&item,1,100);
        if(result<0) {if(errno==EINTR)continue;throw Error("Socket poll failed");}if(!result)continue;
        auto count=writing ? ::send(socket.value,buffer,size,MSG_NOSIGNAL) : ::recv(socket.value,buffer,size,0);
        if(count<0) {if(errno==EAGAIN||errno==EWOULDBLOCK||errno==EINTR)continue;check();throw Error("Socket I/O failed");}
        if(!count){check();throw Closed();}buffer+=count;size-=std::size_t(count);inactive=Clock::now()+std::chrono::seconds(65);
    }
}
Bytes Connection::read() {
    unsigned char header[4];exact(header,4,false);std::uint32_t length=0;for(auto byte:header)length=(length<<8)|byte;
    need(length>0&&length<FrameLimit,"Invalid network frame length");Bytes out(length);exact(out.data(),out.size(),false);return out;
}
void Connection::write(const Bytes &value) {
    need(!value.empty()&&value.size()<FrameLimit,"Invalid outbound frame size");auto size=std::uint32_t(value.size());
    unsigned char header[4]={static_cast<unsigned char>(size>>24),static_cast<unsigned char>(size>>16),static_cast<unsigned char>(size>>8),static_cast<unsigned char>(size)};
    exact(header,4,true);exact(const_cast<unsigned char*>(value.data()),value.size(),true);
}
Bytes packet(const Bytes &header,std::uint64_t offset,const Bytes &body,bool last) {
    auto chunk=add(add(wire::integer(1,last?1:0),wire::integer(2,offset)),wire::blob(3,body));
    auto transfer=add(add(wire::integer(1,1),wire::blob(2,header)),wire::blob(3,chunk));return frame(3,4,transfer);
}
void Connection::sharing(const Bytes &value) {
    auto header=add(add(wire::integer(1,payloadId()),wire::integer(2,1)),wire::integer(3,value.size()));
    secureWrite(packet(header,0,value,false));secureWrite(packet(header,value.size(),{},true));
}
Bytes pairedKey() { return frame(3,4,add(wire::blob(1,randomData(72)),wire::blob(2,randomData(6)))); }
struct Buffer { std::uint64_t total;Bytes value; };
struct Reader {
    Connection &connection;
    std::map<std::uint64_t,Buffer> buffers;
    std::set<std::uint64_t> seen;
    unsigned messages=0;
    explicit Reader(Connection &c):connection(c) {}
    bool auxiliary(const wire::Fields &v1) {
        auto type=number(v1,1);
        if(type==5) {
            auto keep=wire::parse(wire::one(v1,6,2).data);
            if(!number(keep,1))connection.secureWrite(frame(5,6,wire::integer(1,1)));
            return true;
        }
        if(type==4) {
            auto upgrade=wire::parse(wire::one(v1,5,2).data);auto kind=number(upgrade,1);
            need(kind!=2&&kind!=3,"Unsupported transport switch");
            if(kind==1||kind==7) {
                auto failure=wire::integer(1,5);if(wire::has(upgrade,2))failure=add(failure,wire::blob(2,data(upgrade,2)));
                connection.secureWrite(frame(4,5,failure));
            }return true;
        }
        if(type==6)throw Canceled();
        return false;
    }
    wire::Fields next() {
        if(Clock::now()-connection.lastWrite>std::chrono::seconds(10))connection.secureWrite(frame(5,6,wire::integer(1,0)));
        return unwrap(connection.secureRead());
    }
    bool control(const wire::Fields &transfer) {
        auto type=number(transfer,1);
        if(type==3)return true;
        if(type==2) {
            auto command=wire::parse(wire::one(transfer,4,2).data);auto kind=number(command,1);
            if(kind==2)throw Canceled();
            need(kind==3,"Peer reported payload error");return true;
        }
        need(type==1,"Unsupported payload packet");return false;
    }
    Bytes assemble(const wire::Fields &transfer,bool &complete) {
        complete=false;
        auto header=wire::parse(wire::one(transfer,2,2).data),chunk=wire::parse(wire::one(transfer,3,2).data);
        auto id=wire::one(header,1,0).integer,total=wire::one(header,3,0).integer,offset=number(chunk,2),flags=number(chunk,1);
        need(id && number(header,2)==1 && total<=1024*1024 && !(flags&~1ULL),"Invalid sharing payload");
        auto body=data(chunk,3);
        if(!buffers.count(id)) {
            need(!seen.count(id)&&seen.size()<256&&buffers.size()<8,"Too many or repeated sharing payloads");
            seen.insert(id);buffers.emplace(id,Buffer{total,{}});
        }
        auto &buffer=buffers.at(id);
        need(total==buffer.total && offset==buffer.value.size() && body.size()<=total-offset,"Invalid sharing chunk offset");
        buffer.value.insert(buffer.value.end(),body.begin(),body.end());
        if(flags&1) {need(buffer.value.size()==total,"Incomplete sharing payload");auto value=std::move(buffer.value);buffers.erase(id);complete=true;return value;}
        return {};
    }
    Bytes sharing() {
        while(true) {
            connection.check();need(++messages<4096,"Too many negotiation messages");auto v1=next();if(auxiliary(v1))continue;
            need(number(v1,1)==3,"Unexpected negotiation frame");auto transfer=wire::parse(wire::one(v1,4,2).data);
            if(control(transfer))continue;
            bool complete=false;auto value=assemble(transfer,complete);if(!complete)continue;
            auto sharing=unwrap(value);auto type=number(sharing,1);if(type==6)throw Canceled();if(type==5||type==7)continue;return value;
        }
    }
};
void negotiate(Connection &c,Reader &reader) {
    c.sharing(pairedKey());
    auto pke=unwrap(reader.sharing());need(number(pke,1)==3,"Expected paired key encryption");wire::one(pke,4,2);
    c.sharing(frame(4,5,wire::integer(1,3)));
    auto result=unwrap(reader.sharing());need(number(result,1)==4,"Expected paired key result");
    auto status=number(wire::parse(wire::one(result,5,2).data),1);
    need(status==1||status==3,"Peer key verification failed");
}
void safeName(const std::string &name) {
    need(validUtf8(name)&&!name.empty()&&name.size()<=180&&name!="."&&name!="..","Invalid filename");
    for(unsigned char c:name)need(c>=32&&c!=127&&c!='/'&&c!='\\',"Unsafe filename");
}
struct File {
    std::uint64_t id=0,size=0,hash=0,modified=0;
    bool hasHash=false,complete=false;
    std::string name,mime="application/octet-stream",leaf;
    Fd fd;
    std::map<std::uint64_t,std::uint64_t> ranges;
    std::uint64_t received=0;
};
std::vector<File> introduction(const Bytes &message,const std::set<std::uint64_t> &controlIds) {
    auto sharing=unwrap(message);need(number(sharing,1)==1,"Expected file introduction");auto intro=wire::parse(wire::one(sharing,2,2).data);
    std::vector<File> files;std::set<std::uint64_t> ids;std::set<std::string> names;std::uint64_t total=0;
    for(const auto &field:intro) {
        need(field.number!=2&&field.number!=4&&field.number!=5&&field.number!=7,"Only file attachments are supported");
        if(field.number!=1)continue;
        need(field.type==2&&files.size()<64,"Too many files");auto metadata=wire::parse(field.data);File file;
        file.id=wire::one(metadata,3,0).integer;file.size=wire::one(metadata,4,0).integer;file.name=string(wire::one(metadata,1,2).data);
        safeName(file.name);need(file.id && ids.insert(file.id).second && !controlIds.count(file.id),"Invalid or duplicate payload ID");
        need(file.size<=MaxBytes&&file.size<=MaxBytes-total,"Transfer exceeds 8 GiB");total+=file.size;
        need(data(metadata,7).empty(),"Folder attachments are not supported");
        file.mime=wire::has(metadata,5)?string(data(metadata,5)):"application/octet-stream";
        need(validUtf8(file.mime)&&file.mime.size()<=256,"Invalid MIME type");
        file.hasHash=wire::has(metadata,8);file.hash=number(metadata,8);file.leaf=file.name;
        unsigned suffix=0;while(names.count(file.leaf))file.leaf=std::to_string(file.id)+"-"+std::to_string(++suffix)+"-"+file.name;
        need(file.leaf.size()<=255,"Filename too long after deduplication");names.insert(file.leaf);files.push_back(std::move(file));
    }
    need(!files.empty(),"Expected 1..64 files");return files;
}
Bytes consentResponse(unsigned status,const std::vector<File> &files) {
    auto response=wire::integer(1,status);
    if(status==1)for(const auto &file:files)if(file.hasHash) {
        auto payload=add(wire::integer(1,file.id),wire::integer(3,file.size));
        auto payloads=wire::blob(1,payload);
        auto inner=add(wire::integer(1,file.hash),wire::blob(2,payloads));
        auto details=add(wire::integer(1,0),wire::blob(2,inner));
        auto attachment=add(wire::integer(1,1),wire::blob(2,details));
        response=add(response,wire::blob(2,add(wire::integer(1,file.hash),wire::blob(2,attachment))));
    }
    return frame(2,3,response);
}
struct Destination {
    Fd root,stage;
    std::string path,temporary;
    std::vector<File> &files;
    bool published=false;
    Destination(const std::string &folder,std::vector<File> &items):path(folder),files(items) {
        need(!folder.empty()&&folder[0]=='/'&&folder.find('\0')==std::string::npos&&validUtf8(folder),"Invalid destination");
        // The configured root is local, never supplied by the network peer.
        std::string prefix;
        for(std::size_t p=1;p<=folder.size();++p)if(p==folder.size()||folder[p]=='/') {
            prefix=folder.substr(0,p);if(!prefix.empty()&&::mkdir(prefix.c_str(),0700)<0)need(errno==EEXIST,"Cannot create receive directory");
        }
        root=Fd(::open(folder.c_str(),O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW));need(root.value>=0,"Destination is not a real directory");
        struct statvfs space{};need(fstatvfs(root.value,&space)==0&&space.f_frsize>0,"Cannot check free space");
        std::uint64_t required=16*1024*1024;for(const auto &file:files)required+=file.size;
        need(space.f_bavail>=(required+space.f_frsize-1)/space.f_frsize,"Not enough free space");
        temporary=".pending-"+token();need(mkdirat(root.value,temporary.c_str(),0700)==0,"Cannot create private staging directory");
        stage=Fd(openat(root.value,temporary.c_str(),O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW));
        if(stage.value<0){unlinkat(root.value,temporary.c_str(),AT_REMOVEDIR);throw Error("Cannot open staging directory");}
    }
    ~Destination() {
        if(!published && stage.value>=0) {
            for(auto &file:files){file.fd=Fd();unlinkat(stage.value,file.leaf.c_str(),0);}
            stage=Fd();unlinkat(root.value,temporary.c_str(),AT_REMOVEDIR);
        }
    }
    void chunk(File &file,const wire::Fields &header,const wire::Fields &chunk) {
        need(!file.complete&&number(header,2)==2&&wire::one(header,3,0).integer==file.size,"Payload differs from consent");
        need(data(header,6).empty(),"Unexpected payload folder");auto supplied=string(data(header,5));need(supplied.empty()||supplied==file.name,"Filename changed after consent");
        auto offset=wire::one(chunk,2,0).integer,flags=number(chunk,1);auto body=data(chunk,3);
        need(!(flags&~1ULL)&&offset<=file.size&&body.size()<=file.size-offset,"Invalid file chunk bounds");
        if(file.fd.value<0) {file.fd=Fd(openat(stage.value,file.leaf.c_str(),O_CREAT|O_EXCL|O_RDWR|O_CLOEXEC|O_NOFOLLOW,0600));need(file.fd.value>=0,"Cannot create private file");}
        if(!body.empty()) {
            auto end=offset+body.size();auto after=file.ranges.upper_bound(offset);auto before=after;
            bool duplicate=false;if(before!=file.ranges.begin()){--before;if(before->second>offset){need(before->second>=end,"Overlapping file chunks");duplicate=true;}}
            if(duplicate) {
                Bytes existing(body.size());std::size_t done=0;
                while(done<existing.size()){auto n=pread(file.fd.value,existing.data()+done,existing.size()-done,offset+done);if(n<0&&errno==EINTR)continue;need(n>0,"Cannot verify repeated chunk");done+=std::size_t(n);}
                need(existing==body,"Conflicting repeated chunk");
            } else {
                need(after==file.ranges.end()||after->first>=end,"Overlapping file chunks");need(file.ranges.size()<4096,"Too many sparse file ranges");
                std::size_t done=0;while(done<body.size()){auto n=pwrite(file.fd.value,body.data()+done,body.size()-done,offset+done);if(n<0&&errno==EINTR)continue;need(n>0,"File write failed");done+=std::size_t(n);}
                file.received+=body.size();auto begin=offset;
                if(before!=file.ranges.end()&&before->second==offset){begin=before->first;file.ranges.erase(before);}
                auto next=file.ranges.find(end);if(next!=file.ranges.end()){end=next->second;file.ranges.erase(next);}
                file.ranges.emplace(begin,end);
            }
        }
        if(flags&1) {
            need(offset+body.size()==file.size&&file.received==file.size,"Incomplete terminal file chunk");
            need(file.size==0||(file.ranges.size()==1&&file.ranges.begin()->first==0&&file.ranges.begin()->second==file.size),"Missing file ranges");
            struct stat st{};need(fstat(file.fd.value,&st)==0&&std::uint64_t(st.st_size)==file.size&&fsync(file.fd.value)==0,"File completion failed");
            file.fd=Fd();file.complete=true;
        }
    }
    std::string publish() {
        for(const auto &file:files)need(file.complete,"Cannot publish incomplete batch");
        need(fsync(stage.value)==0,"Staging synchronization failed");
        std::string target="transfer-"+token();
        need(syscall(SYS_renameat2,root.value,temporary.c_str(),root.value,target.c_str(),1)==0,"Cannot publish receive batch atomically");
        published=true;fsync(root.value);return path+"/"+target;
    }
};
Fd connectSocket(const std::string &host,int port,Context &context) {
    need(port>0&&port<=65535,"Invalid peer port");sockaddr_in address{};address.sin_family=AF_INET;address.sin_port=htons(std::uint16_t(port));
    need(inet_pton(AF_INET,host.c_str(),&address.sin_addr)==1,"Peer address must be IPv4");
    Fd socket(::socket(AF_INET,SOCK_STREAM|SOCK_CLOEXEC|SOCK_NONBLOCK,0));need(socket.value>=0,"Cannot create TCP socket");
    int result=::connect(socket.value,reinterpret_cast<sockaddr*>(&address),sizeof(address));
    if(result<0)need(errno==EINPROGRESS,"Initial connect failed");
    Time end=Clock::now()+std::chrono::seconds(10);
    while(result<0) {
        if(context.stop||signaled)throw Canceled();
        need(Clock::now()<end,"Initial connect timed out");pollfd item{socket.value,POLLOUT,0};int ready=poll(&item,1,100);
        if(ready<0&&errno==EINTR)continue;
        need(ready>=0,"Connect poll failed");if(!ready)continue;
        int error=0;socklen_t length=sizeof(error);need(getsockopt(socket.value,SOL_SOCKET,SO_ERROR,&error,&length)==0&&error==0,"Initial connect failed");break;
    }
    int yes=1;setsockopt(socket.value,IPPROTO_TCP,TCP_NODELAY,&yes,sizeof(yes));return socket;
}
void handshake(Connection &c,bool client,const std::string &name,std::string &source,unsigned &safe) {
    Handshake exchange(client?Role::Client:Role::Server);
    if(client) {
        c.write(connectionRequest(name));c.write(exchange.start());c.write(exchange.consume(c.read()));
        c.write(connectionResponse());safe=validateResponse(c.read());
    } else {
        auto request=unwrap(c.read());need(number(request,1)==1,"Expected connection request");source=senderName(wire::parse(wire::one(request,2,2).data));
        c.write(exchange.consume(c.read()));exchange.consume(c.read());c.write(connectionResponse());safe=validateResponse(c.read());
    }
    c.session=exchange.takeSession();c.deadline=Clock::now()+std::chrono::seconds(65);
}
void progress(Connection &c,bool sending,std::uint64_t transferred,std::uint64_t total) {
    auto fraction=total?double(transferred)/double(total):1.;
    if(sending)event({{"state",quoteJson("running")},{"pin",quoteJson(c.session->verificationPin())},{"progress",std::to_string(fraction)},{"bytes",std::to_string(transferred)},{"total",std::to_string(total)}});
    else event({{"event",quoteJson("progress")},{"id",quoteJson(c.id)},{"progress",std::to_string(fraction)},{"bytes",std::to_string(transferred)},{"total",std::to_string(total)}});
}
void receiveConnection(std::shared_ptr<Connection> c,const std::string &destination) {
    bool requested=false;
    try {
        std::string source;unsigned safe=0;handshake(*c,false,"",source,safe);Reader reader(*c);negotiate(*c,reader);
        auto introductionFrame=reader.sharing();std::vector<File> files;
        try { files=introduction(introductionFrame,reader.seen); }
        catch(...) {c->sharing(consentResponse(4,files));throw;}
        std::string names="[";std::uint64_t total=0;
        for(const auto &file:files){if(names.size()>1)names+=',';names+=quoteJson(file.name);total+=file.size;}names+=']';
        c->deadline=Clock::now()+std::chrono::seconds(45);c->waiting=true;
        requested=true;
        event({{"event",quoteJson("request")},{"id",quoteJson(c->id)},{"sender",quoteJson(source)},{"pin",quoteJson(c->session->verificationPin())},{"files",names},{"total",std::to_string(total)}});
        while(c->consent<0) {
            c->check();pollfd item{c->socket.value,POLLIN,0};int available=poll(&item,1,100);
            if(available<0&&errno==EINTR)continue;
            need(available>=0,"Consent poll failed");
            if(available>0) {
                auto v1=reader.next();if(reader.auxiliary(v1))continue;
                need(number(v1,1)==3,"Unexpected data before consent");auto transfer=wire::parse(wire::one(v1,4,2).data);
                if(reader.control(transfer))continue;
                bool complete=false;auto incoming=reader.assemble(transfer,complete);
                if(complete){auto sharing=unwrap(incoming);if(number(sharing,1)==6)throw Canceled();need(number(sharing,1)==7||number(sharing,1)==5,"Unexpected sharing data before consent");}
            }
        }
        c->waiting=false;
        if(c->consent==0){c->sharing(consentResponse(2,files));event({{"event",quoteJson("rejected")},{"id",quoteJson(c->id)}});c->done=true;return;}
        Destination storage(destination,files);c->sharing(consentResponse(1,files));c->deadline=Clock::now()+std::chrono::minutes(30);
        std::map<std::uint64_t,File*> allowed;for(auto &file:files)allowed.emplace(file.id,&file);
        unsigned completed=0;Time update=Clock::now();
        while(completed<files.size()) {
            auto v1=reader.next();if(reader.auxiliary(v1))continue;need(number(v1,1)==3,"Unexpected file transfer frame");
            auto transfer=wire::parse(wire::one(v1,4,2).data);if(reader.control(transfer))continue;
            auto header=wire::parse(wire::one(transfer,2,2).data),chunk=wire::parse(wire::one(transfer,3,2).data);
            if(number(header,2)==1) {
                bool complete=false;auto incoming=reader.assemble(transfer,complete);
                if(complete){auto sharing=unwrap(incoming);if(number(sharing,1)==6)throw Canceled();need(number(sharing,1)==5||number(sharing,1)==7,"Unexpected sharing message during transfer");}continue;
            }
            auto id=wire::one(header,1,0).integer;need(allowed.count(id),"Unannounced file payload");auto &file=*allowed.at(id);
            storage.chunk(file,header,chunk);if(file.complete)++completed;
            if(file.complete||Clock::now()-update>std::chrono::milliseconds(200)) {
                std::uint64_t received=0;for(const auto &item:files)received+=item.received;progress(*c,false,received,total);update=Clock::now();
            }
        }
        std::string saved=storage.publish();
        try {c->secureWrite(frame(6,7,{}));}catch(...){}
        event({{"event",quoteJson("received")},{"id",quoteJson(c->id)},{"destination",quoteJson(saved)},{"count",std::to_string(files.size())}});
    } catch(const Closed &error) {
        // Discovery peers may open a TCP connection and leave without offering
        // files. Only a disconnect after an introduction interrupts a transfer.
        c->waiting=false;
        if(requested)event({{"event",quoteJson("ended")},{"id",quoteJson(c->id)},{"error",quoteJson(error.what())}});
    } catch(const std::exception &error) {
        c->waiting=false;event({{"event",quoteJson("ended")},{"id",quoteJson(c->id)},{"error",quoteJson(error.what())}});
    }
    c->done=true;
}
std::vector<File> sources(const Json &config) {
    const auto &paths=config.at("files");need(paths.kind==Json::Array&&!paths.array.empty()&&paths.array.size()<=64,"Expected 1..64 source files");
    std::vector<File> files;std::set<std::uint64_t> ids;std::uint64_t total=0;
    for(const auto &path:paths.array) {
        std::string name=path.string();need(name.find('\0')==std::string::npos,"Invalid source path");File file;
        file.fd=Fd(open(name.c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW));struct stat st{};
        need(file.fd.value>=0&&fstat(file.fd.value,&st)==0&&S_ISREG(st.st_mode),"Source is not a regular file");
        need(st.st_size>=0&&std::uint64_t(st.st_size)<=MaxBytes-total,"Source files exceed 8 GiB");file.size=std::uint64_t(st.st_size);total+=file.size;
        file.name=name.substr(name.find_last_of('/')==std::string::npos?0:name.find_last_of('/')+1);safeName(file.name);
        do {file.id=payloadId();}while(!ids.insert(file.id).second);
        file.modified=std::uint64_t(st.st_mtim.tv_sec)*1000+std::uint64_t(st.st_mtim.tv_nsec/1000000);
        auto extension=file.name.find_last_of('.');std::string ext=extension==std::string::npos?"":file.name.substr(extension);
        std::transform(ext.begin(),ext.end(),ext.begin(),[](unsigned char c){return char(std::tolower(c));});
        if(ext==".jpg"||ext==".jpeg")file.mime="image/jpeg";else if(ext==".png")file.mime="image/png";else if(ext==".pdf")file.mime="application/pdf";else if(ext==".txt")file.mime="text/plain";
        files.push_back(std::move(file));
    }return files;
}
void sendFiles(Context &context,const Json &config) {
    auto files=sources(config);std::uint64_t total=0;for(const auto &file:files)total+=file.size;
    auto port=config.at("port").integer();need(port>0&&port<=65535,"Invalid peer port");
    auto socket=connectSocket(config.at("host").string(),int(port),context);
    auto c=std::make_shared<Connection>(socket.value,&context);socket.value=-1;
    {std::lock_guard<std::mutex> lock(context.mutex);context.connections[c->id]=c;}
    std::string unused;unsigned safe=0;handshake(*c,true,config.at("name").string(),unused,safe);Reader reader(*c);negotiate(*c,reader);
    Bytes intro;
    for(const auto &file:files) {
        auto metadata=add(wire::blob(1,bytes(file.name)),wire::integer(2,file.mime.find("image/")==0?1:0));
        metadata=add(metadata,wire::integer(3,file.id));metadata=add(metadata,wire::integer(4,file.size));
        metadata=add(metadata,wire::blob(5,bytes(file.mime)));metadata=add(metadata,wire::integer(6,file.id));
        intro=add(intro,wire::blob(1,metadata));
    }
    intro=add(intro,wire::integer(8,1));c->sharing(frame(1,2,intro));
    event({{"state",quoteJson("waiting")},{"pin",quoteJson(c->session->verificationPin())}});
    c->deadline=Clock::now()+std::chrono::seconds(65);auto response=unwrap(reader.sharing());
    need(number(response,1)==2,"Expected receive approval");need(number(wire::parse(wire::one(response,3,2).data),1)==1,"Peer rejected transfer");
    c->deadline=Clock::now()+std::chrono::minutes(30);std::uint64_t sent=0;Time update=Clock::now();
    for(auto &file:files) {
        auto header=add(add(wire::integer(1,file.id),wire::integer(2,2)),wire::integer(3,file.size));
        header=add(header,wire::blob(5,bytes(file.name)));header=add(header,wire::blob(6,{}));header=add(header,wire::integer(7,file.modified));
        std::uint64_t offset=0;
        while(offset<file.size) {
            c->check();Bytes body(std::size_t(std::min<std::uint64_t>(512*1024,file.size-offset)));std::size_t read=0;
            while(read<body.size()){auto n=pread(file.fd.value,body.data()+read,body.size()-read,offset+read);if(n<0&&errno==EINTR)continue;need(n>0,"Source file changed or could not be read");read+=std::size_t(n);}
            c->secureWrite(packet(header,offset,body,false));offset+=body.size();sent+=body.size();
            if(Clock::now()-update>std::chrono::milliseconds(200)){progress(*c,true,sent,total);update=Clock::now();}
            for(unsigned i=0;i<16;++i) {
                pollfd item{c->socket.value,POLLIN,0};if(poll(&item,1,0)<=0)break;
                auto v1=reader.next();if(reader.auxiliary(v1))continue;
                need(number(v1,1)==3,"Unexpected sender-side control frame");auto transfer=wire::parse(wire::one(v1,4,2).data);
                if(reader.control(transfer))continue;
                bool complete=false;auto value=reader.assemble(transfer,complete);
                if(complete&&number(unwrap(value),1)==6)throw Canceled();
            }
        }
        struct stat st{};need(fstat(file.fd.value,&st)==0&&std::uint64_t(st.st_size)==file.size&&
            std::uint64_t(st.st_mtim.tv_sec)*1000+std::uint64_t(st.st_mtim.tv_nsec/1000000)==file.modified,"Source changed during transfer");
        c->secureWrite(packet(header,file.size,{},true));progress(*c,true,sent,total);
    }
    // Windows safe-disconnect version 0 must finalize before we close TCP.
    if(safe>=1) {
        try { c->secureWrite(frame(6,7,wire::integer(1,1))); }
        catch(const Canceled&) { throw; }
        catch(const Error&) { /* A completed receiver may already have sent its final frame and FIN. */ }
    }
    c->deadline=Clock::now()+std::chrono::seconds(60);
    try {
        while(true) {
            auto v1=reader.next();
            if(number(v1,1)==6) {
                auto finish=wire::parse(wire::one(v1,7,2).data);
                if(number(finish,1)) { try { c->secureWrite(frame(6,7,wire::integer(2,1))); } catch(const Error&) {} }
                break;
            }
            if(reader.auxiliary(v1))continue;
            if(number(v1,1)==3){auto transfer=wire::parse(wire::one(v1,4,2).data);if(reader.control(transfer))continue;bool complete=false;auto value=reader.assemble(transfer,complete);if(complete&&number(unwrap(value),1)==6)throw Canceled();}
        }
    }catch(const Closed&){need(safe==0,"Peer closed without transfer completion confirmation");}
    event({{"state",quoteJson("finished")},{"progress","1.0"}});
}
void receiver(Context &context,const Json &config) {
    std::string bind=config.at("bind").string(),name=config.at("name").string(),destination=config.at("destination").string();
    auto configuredPort=config.has("port")?config.at("port").integer():0;
    need(configuredPort>=0&&configuredPort<=65535,"Invalid listening port");int port=int(configuredPort);
    sockaddr_in address{};address.sin_family=AF_INET;address.sin_port=htons(std::uint16_t(port));need(inet_pton(AF_INET,bind.c_str(),&address.sin_addr)==1,"Invalid bind address");
    Fd listener(socket(AF_INET,SOCK_STREAM|SOCK_CLOEXEC|SOCK_NONBLOCK,0));need(listener.value>=0,"Cannot create listening socket");int yes=1;
    setsockopt(listener.value,SOL_SOCKET,SO_REUSEADDR,&yes,sizeof(yes));
    need(::bind(listener.value,reinterpret_cast<sockaddr*>(&address),sizeof(address))==0&&listen(listener.value,4)==0,"Cannot listen on local address");
    socklen_t size=sizeof(address);need(getsockname(listener.value,reinterpret_cast<sockaddr*>(&address),&size)==0,"Cannot determine port");
    auto info=endpoint(name);static const char alphabet[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";std::string encoded;
    unsigned bits=0,value=0;for(auto byte:info){value=(value<<8)|byte;bits+=8;while(bits>=6){bits-=6;encoded+=alphabet[(value>>bits)&63];}}if(bits)encoded+=alphabet[(value<<(6-bits))&63];
    event({{"event",quoteJson("listening")},{"port",std::to_string(ntohs(address.sin_port))},{"endpoint",quoteJson(encoded)}});
    struct Worker {std::shared_ptr<Connection> connection;std::thread thread;};std::list<Worker> workers;
    while(!context.stop&&!signaled) {
        for(auto i=workers.begin();i!=workers.end();) {
            if(i->connection->done){i->thread.join();{std::lock_guard<std::mutex> lock(context.mutex);context.connections.erase(i->connection->id);}i=workers.erase(i);}else ++i;
        }
        pollfd item{listener.value,POLLIN,0};int ready=poll(&item,1,100);if(ready<0){if(errno==EINTR)continue;break;}if(!ready)continue;
        Fd accepted(accept4(listener.value,nullptr,nullptr,SOCK_CLOEXEC|SOCK_NONBLOCK));if(accepted.value<0)continue;if(workers.size()>=3)continue;
        setsockopt(accepted.value,IPPROTO_TCP,TCP_NODELAY,&yes,sizeof(yes));auto c=std::make_shared<Connection>(accepted.value,&context);accepted.value=-1;
        {std::lock_guard<std::mutex> lock(context.mutex);context.connections[c->id]=c;}
        workers.push_back(Worker{c,std::thread(receiveConnection,c,destination)});
    }
    context.cancelAll();for(auto &worker:workers)worker.thread.join();
}
void controlPipe(Context &context) {
    std::string buffer;
    while(!context.finished&&!context.stop) {
        if(signaled){context.cancelAll();break;}pollfd item{STDIN_FILENO,POLLIN,0};int ready=poll(&item,1,100);
        if(ready<0){if(errno==EINTR)continue;context.cancelAll();break;}if(!ready)continue;
        char block[4096];auto count=::read(STDIN_FILENO,block,sizeof(block));if(count<0&&errno==EINTR)continue;
        if(count<=0){context.cancelAll();break;}buffer.append(block,std::size_t(count));
        if(buffer.size()>65536){context.cancelAll();break;}
        for(auto end=buffer.find('\n');end!=std::string::npos;end=buffer.find('\n')) {
            auto line=buffer.substr(0,end);buffer.erase(0,end+1);
            try {
                auto config=parseJson(line);auto command=config.at("command").string();
                if(command=="stop"){context.cancelAll();return;}
                if(command=="cancel"&&!config.has("id")){context.cancelAll();return;}
                if(!config.has("id"))continue;
                std::shared_ptr<Connection> c;
                {std::lock_guard<std::mutex> lock(context.mutex);auto i=context.connections.find(config.at("id").string());if(i!=context.connections.end())c=i->second;}
                if(!c)continue;
                if(command=="cancel")c->cancel();
                else if(command=="approve"&&c->waiting){int expected=-1;c->consent.compare_exchange_strong(expected,config.at("accepted").flag()?1:0);}
            }catch(const std::exception&){/* A malformed local command never grants consent. */}
        }
    }
}
}
#ifndef QUICKSHARE_WORKER_UNIT_TEST
int main(int argc,char **argv) {
    if(argc==2&&std::string(argv[1])=="--capabilities") {
        std::cout<<"{\"backend\":\"cpp\",\"fileTransfer\":true,\"medium\":\"wifi-lan\",\"maxFiles\":64}\n";return 0;
    }
    umask(0077);std::signal(SIGPIPE,SIG_IGN);std::signal(SIGTERM,signalHandler);std::signal(SIGINT,signalHandler);
    Context context;std::thread commands;
    try {
        std::string line;while(true){char c;auto n=::read(STDIN_FILENO,&c,1);if(n<0&&errno==EINTR)continue;need(n==1,"Missing worker configuration");if(c=='\n')break;need(line.size()<65536,"Worker configuration too large");line+=c;}
        auto config=parseJson(line);auto mode=config.at("command").string();need(mode=="send"||mode=="receive","Unsupported worker command");
        commands=std::thread(controlPipe,std::ref(context));
        if(mode=="send")sendFiles(context,config);else receiver(context,config);
        context.finished=true;if(commands.joinable())commands.join();return 0;
    }catch(const Canceled&) {context.finished=true;context.cancelAll();if(commands.joinable())commands.join();event({{"state",quoteJson("canceled")}});return 0;}
    catch(const std::exception &error) {context.finished=true;context.cancelAll();if(commands.joinable())commands.join();event({{"state",quoteJson("failed")},{"error",quoteJson(error.what())}});return 1;}
}
#endif
