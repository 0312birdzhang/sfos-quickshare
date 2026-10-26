// SPDX-License-Identifier: GPL-3.0-or-later
#define QUICKSHARE_WORKER_UNIT_TEST
#include "../src/worker.cpp"
#include <functional>
namespace {
unsigned checks=0;
void check(bool result) {need(result,"Worker unit assertion failed");++checks;}
void rejects(const std::function<void()> &fn) {try{fn();}catch(const Error&){++checks;return;}throw Error("Invalid input accepted");}
Bytes metadata(const std::string &name,std::uint64_t id=1,std::uint64_t size=3,const std::string &folder="") {
    auto value=add(add(wire::blob(1,bytes(name)),wire::integer(3,id)),wire::integer(4,size));
    if(!folder.empty())value=add(value,wire::blob(7,bytes(folder)));return value;
}
std::vector<File> files(const std::string &name="test.txt",std::uint64_t size=3) {
    return introduction(frame(1,2,wire::blob(1,metadata(name,1,size))),{});
}
wire::Fields header(const std::string &name="test.txt",std::uint64_t size=3) {
    return wire::parse(add(add(add(wire::integer(1,1),wire::integer(2,2)),wire::integer(3,size)),wire::blob(5,bytes(name))));
}
wire::Fields chunk(std::uint64_t offset,const std::string &body,bool last=false) {
    return wire::parse(add(add(wire::integer(1,last?1:0),wire::integer(2,offset)),wire::blob(3,bytes(body))));
}
}
int main() {
    try {
        check(parseJson("{\"x\":\"\\u4e2d\\ud83d\\ude00\",\"b\":true}").at("x").string()=="中😀");
        check(parseJson("{\"n\":-9223372036854775808}").at("n").integer()==INT64_MIN);
        for(const auto &invalid:{"{\"x\":1,\"x\":2}","{\"x\":01}","{\"x\":1.1}","\"\\ud800\"","\"\\udc00\"","[true,]","9223372036854775808"})rejects([&]{parseJson(invalid);});
        for(const auto &name:{std::string("../x"),std::string("a/b"),std::string("a\\b"),std::string("."),std::string(".."),std::string(""),std::string("a\0b",3),std::string("bad\nfile"),std::string("\xff",1)})rejects([&]{files(name);});
        rejects([]{files("too-big",MaxBytes+1);});
        rejects([]{introduction(frame(1,2,wire::blob(1,metadata("folder",1,3,"dir"))),{});});
        rejects([]{introduction(frame(1,2,add(wire::blob(1,metadata("a")),wire::blob(1,metadata("b")))),{});});
        rejects([]{introduction(frame(1,2,wire::blob(1,metadata("control-collision"))),{1});});
        rejects([]{introduction(frame(1,2,wire::blob(2,{})),{});});
        auto unicode=files("中文😀.pdf",0);check(unicode[0].name=="中文😀.pdf");
        auto duplicate=introduction(frame(1,2,add(wire::blob(1,metadata("same",1)),wire::blob(1,metadata("same",2)))),{});
        check(duplicate[0].leaf!=duplicate[1].leaf);
        char temporary[]="/tmp/quickshare-native-tests-XXXXXX";need(mkdtemp(temporary)!=nullptr,"Cannot make test directory");std::string root=temporary;
        {
            auto items=files();Destination destination(root+"/good",items);
            destination.chunk(items[0],header(),chunk(0,"abc"));
            destination.chunk(items[0],header(),chunk(0,"abc")); // Identical retry.
            check(items[0].received==3);
            rejects([&]{destination.chunk(items[0],header(),chunk(0,"xyz"));});
            destination.chunk(items[0],header(),chunk(3,"",true));
            auto saved=destination.publish();struct stat st{};check(stat((saved+"/test.txt").c_str(),&st)==0&&st.st_size==3&&(st.st_mode&0777)==0600);
            unlink((saved+"/test.txt").c_str());rmdir(saved.c_str());
        }
        {
            auto items=files();Destination destination(root+"/partial",items);auto stage=destination.temporary;
            destination.chunk(items[0],header(),chunk(0,"a"));
            rejects([&]{destination.chunk(items[0],header(),chunk(3,"",true));});
            rejects([&]{destination.publish();});
            rejects([&]{destination.chunk(items[0],header("changed.txt"),chunk(1,"bc"));});
            rejects([&]{destination.chunk(items[0],header(),chunk(2,"XX"));});
        }
        {
            auto items=files("empty",0);Destination destination(root+"/empty",items);
            destination.chunk(items[0],header("empty",0),chunk(0,"",true));auto saved=destination.publish();
            struct stat st{};check(stat((saved+"/empty").c_str(),&st)==0&&st.st_size==0);unlink((saved+"/empty").c_str());rmdir(saved.c_str());
        }
        mkdir((root+"/outside").c_str(),0700);need(symlink((root+"/outside").c_str(),(root+"/linked").c_str())==0,"Test symlink failed");
        rejects([&]{auto items=files();Destination destination(root+"/linked",items);});
        unlink((root+"/linked").c_str());rmdir((root+"/outside").c_str());
        // All failed staging directories must already have been removed by RAII.
        check(rmdir((root+"/partial").c_str())==0);
        rmdir((root+"/good").c_str());rmdir((root+"/empty").c_str());rmdir(root.c_str());
        std::cout<<checks<<" worker safety checks PASS\n";return 0;
    }catch(const std::exception &error){std::cerr<<"FAIL: "<<error.what()<<'\n';return 1;}
}
