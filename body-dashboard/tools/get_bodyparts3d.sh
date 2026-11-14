#!/bin/sh
# Downloads the BodyParts3D meshes (about 1.3 GB) into tools/_src/. Only needed if you want to rebuild the anatomy data.
set -e
cd "$(dirname "$0")"; mkdir -p _src && cd _src
[ -d BodyParts3D ] || git clone --depth 1 https://github.com/Kevin-Mattheus-Moerman/BodyParts3D
