#!/usr/bin/env bash

set -e  # Stop when a command fails

# Temporary, will be  automatic once tests are complete
find Tests/ -type f -iname "test_*.py" | xargs python3 -m unittest
