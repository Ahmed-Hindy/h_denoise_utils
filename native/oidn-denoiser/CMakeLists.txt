cmake_minimum_required(VERSION 3.23)
project(Denoiser VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(GNUInstallDirs)

set(OIDN_ROOT "" CACHE PATH "Path to the official Intel Open Image Denoise package root")
if(OIDN_ROOT)
    list(APPEND CMAKE_PREFIX_PATH "${OIDN_ROOT}")
endif()

find_package(OpenImageIO CONFIG REQUIRED)
find_package(OpenEXR CONFIG REQUIRED)
find_package(Imath CONFIG REQUIRED)
find_package(OpenImageDenoise CONFIG REQUIRED)

add_executable(Denoiser src/main.cpp)

target_link_libraries(Denoiser
    PRIVATE
        openimageio::openimageio
        OpenEXR::OpenEXR
        Imath::Imath
        OpenImageDenoise)

target_compile_definitions(Denoiser PRIVATE NOMINMAX)

if(MSVC)
    target_compile_options(Denoiser PRIVATE /W4 /permissive-)
else()
    target_compile_options(Denoiser PRIVATE -Wall -Wextra -Wpedantic)
endif()

install(TARGETS Denoiser RUNTIME DESTINATION .)
