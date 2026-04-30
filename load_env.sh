#!/bin/sh

# check if there is a .venv folder
if [ -d ".venv" ]; then
    echo "Activating virtual environment"
    . .venv/bin/activate
else
    echo "No virtual environment found, assuming global python environment"
fi

echo "Adding tools/bin and tools/helpers to PATH"
export PATH=$PATH:$(pwd)/tools/bin:$(pwd)/tools/helpers
export PYTHONPATH=$PYTHONPATH:$(pwd)
