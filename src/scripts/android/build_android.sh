#!/bin/bash
#!/bin/sh

set -e
comment "build_android.sh"

# ARGUMENTS 
# Set this to your minSdkVersion.
export API=$1
export BuildType=$2

if [ -z $BUILD_SOURCESDIRECTORY ]; then 
    BUILD_SOURCESDIRECTORY='../../..'
fi

if [ -z $API ]; then
    echo "No API version was provided"
    exit 1
fi

# androidtoolsdir
# /opt/android-sdk

# Please refer to https://developer.android.com/ndk/guides/other_build_systems#autoconf for documentation

NDK=/opt/android-sdk/ndk/android-ndk-r21d
export ANDROID_NDK_ROOT=$NDK
export ANDROID_NDK_HOME=$NDK
HOST="linux-x86_64"

export TOOLCHAIN=$NDK/toolchains/llvm/prebuilt/$HOST
# export SYSROOT=$TOOLCHAIN/sysroot
export PATH=$TOOLCHAIN/bin:$NDK/toolchains/arm-linux-androideabi-4.9/prebuilt/$HOST/bin:$PATH

function buildLibraries {
    abi=$1
    comment "build_android.buildLibraries $abi"
    outputFolder=""
    if [[ $abi == "android-arm" ]]; then
        export TARGET=armv7a-linux-androideabi
        outputFolder="armeabi-v7a"
    elif [[ $abi == "android-arm64" ]]; then
        export TARGET=aarch64-linux-android
        outputFolder="arm64-v8a"
    elif [[ $abi == "android-x86" ]]; then
        export TARGET=i686-linux-android
        outputFolder="x86"
    elif [[ $abi == "android-x86_64" ]]; then
        export TARGET=x86_64-linux-android
        outputFolder="x86_64"
    else 
        echo "Unknown ABI: $abi"
        return
    fi

    # Configure and build.
    # export AR=$TOOLCHAIN/bin/$TARGET-ar
    # export AS=$TOOLCHAIN/bin/$TARGET-as
    # export CC=$TOOLCHAIN/bin/$TARGET$API-clang
    # export CXX=$TOOLCHAIN/bin/$TARGET$API-clang++
    # export LD=$TOOLCHAIN/bin/$TARGET-ld
    # export RANLIB=$TOOLCHAIN/bin/$TARGET-ranlib
    # export STRIP=$TOOLCHAIN/bin/$TARGET-strip
    # export NM=$TOOLCHAIN/bin/$TARGET-nm

    runq "rm -r build_android"
    runq "mkdir build_android"
    runq "cd build_android"
    runq "cmake -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake -DANDROID_ABI=$outputFolder -DANDROID_NATIVE_API_LEVEL=$API -DCMAKE_BUILD_TYPE=$BuildType -DOPENSSL_CRYPTO_LIBRARY=${ANDROID}/$outputFolder/lib -DOPENSSL_INCLUDE_DIR=${ANDROID}/$outputFolder/include --config $BuildType -B. -S.."
    runq make

    if [[ $? != 0 ]]; then
        warning "[ERROR] Make failed"
        exit 1
    fi

    comment "${outputFolder} build successful"

    runq "cp ./src/c++/fuzzyvault/*.so ${ANDROID}/$outputFolder/lib"
    runq "cp ./src/c++/fuzzyvault/*.a ${ANDROID}/$outputFolder/lib"
    runq "cp ../src/c++/fuzzyvault/fuzzy.h ${ANDROID}/$outputFolder/include/"

    runq "cd .."
}
cd $BUILD_SOURCESDIRECTORY

buildLibraries android-arm
buildLibraries android-x86_64
buildLibraries android-arm64
buildLibraries android-x86
