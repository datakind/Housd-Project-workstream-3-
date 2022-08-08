#!/bin/sh

# Lake county
python3 src/event-siting.py -f configs/lake-config.yaml

# Orange county
python3 src/event-siting.py -f configs/orange-config.yaml

# Seminole county
python3 src/event-siting.py -f configs/seminole-config.yaml

# Osceola county
python3 src/event-siting.py -f configs/osceola-config.yaml
