#!/bin/sh

# This script is used to install symlinks to the sns scripts in the .venv or user supplied directory

TARGET=.venv/bin

if [ -n "$1" ]; then
    TARGET=$1
fi

if [ ! -d $TARGET ]; then
    echo "Target directory $TARGET does not exist"
    exit 1
fi

echo "Installing symlinks to sns scripts in $TARGET"
for script in tools/bin/*; do
    echo "Linking $script to $TARGET/$(basename $script)"
    ln -sf $(pwd)/$script $TARGET/$(basename $script)
done


for script in tools/helpers/*; do
    echo "Linking $script to $TARGET/$(basename $script)"
    ln -sf $(pwd)/$script $TARGET/$(basename $script)
done

echo "export PYTHONPATH=\"$(pwd):\$PYTHONPATH\"" >> .venv/bin/activate

echo "Done"
