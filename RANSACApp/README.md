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
    
    
***DISCLAIMER: I DO NOT OWN THE LINCENCE TO THIS CODE. Distributed under the terms of the GNU Lesser General Public License (LGPL v3.0). See COPYING and COPYING.LESSER for license details. ***

Copyright (C) 2018 Pupil Labs

All Rights Reserved.

This is Pye3d by Pupil Labs
