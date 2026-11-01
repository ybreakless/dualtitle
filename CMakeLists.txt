cmake_minimum_required(VERSION 3.16)
project(DualTitle VERSION 5.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(WIN32)
    add_executable(DualTitle src/DualTitle.cpp src/DualTitle.rc)
    # The manifest ships embedded via DualTitle.rc; disable the linker-side merge.
    set_target_properties(DualTitle PROPERTIES
        LINK_FLAGS "/MANIFEST:NO /SUBSYSTEM:WINDOWS")
    target_link_libraries(DualTitle PRIVATE
        user32 gdi32 shell32 comdlg32 gdiplus uxtheme winmm)
else()
    add_executable(DualTitle src/DualTitle.cpp)
endif()
