cmake_minimum_required(VERSION 3.15)
project(EvaTool)

set(CMAKE_CXX_STANDARD 17)

# 寻找第三方库
find_package(Boost REQUIRED COMPONENTS locale)
find_package(ZLIB REQUIRED)

# 包含路径
include_directories(include third_party)

# 定义可执行文件
add_executable(unpacker 
    src/archiver/unpacker.cpp
)

add_executable(repacker
    src/archiver/repacker.cpp
)

# 链接
target_link_libraries(unpacker 
    PRIVATE 
    Boost::locale
    ZLIB::ZLIB
)

target_link_libraries(repacker
    PRIVATE
    Boost::locale
    ZLIB::ZLIB
)