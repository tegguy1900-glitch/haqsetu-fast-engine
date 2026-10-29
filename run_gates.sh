#!/bin/bash

python core/run_application_demo.py

if [ $? -eq 0 ]; then
    echo "application_engine GREEN" >> .agent/progress.txt
    git add .agent/progress.txt
    git commit -m "Add application engine progress"
else
    echo "application_engine RED" >> .agent/progress.txt
    git add .agent/progress.txt
    git commit -m "Add application engine progress"
fi

python core/run_ui_application_demo.py

if [ $? -eq 0 ]; then
    echo "ui_application GREEN" >> .agent/progress.txt
    git add .agent/progress.txt
    git commit -m "Add UI application progress"
else
    echo "ui_application RED" >> .agent/progress.txt
    git add .agent/progress.txt
    git commit -m "Add UI application progress"
fi
