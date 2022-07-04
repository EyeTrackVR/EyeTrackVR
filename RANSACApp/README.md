# How to spin up a dev environment

firstly, ensure that the virtualenv module is installed onto your pc. 

    pip install virtualenv
    
Next, cd into the RANSACApp directory and run:

    python -m virtualenv venv
    
On windows, next we run:

    venv\Scripts\activate
    
On linux we run:

    source venv\Scripts\activate
    
Next, we install the dependancies and build:

    pip install -r requirements.txt
    
When that is complete, move on to building:
    
    pyinstaller eyetrackapp.spec

Now we can run the executable:

    cd dist/eyetrackapp
    
    ./eyetrackapp
    
