cmake_minimum_required(VERSION 3.16)
project(DualTitle VERSION 4.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(WIN32)
    add_executable(DualTitle src/DualTitle.cpp src/DualTitle.rc)
    target_link_libraries(DualTitle PRIVATE user32 gdi32 shell32 comdlg32)
else()
    add_executable(DualTitle src/DualTitle.cpp)
endif()
