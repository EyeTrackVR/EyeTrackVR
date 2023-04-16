:: Example script to auto build app and make an installer
:: File paths will all need to be updated to your setup
cd C:\Users\beaul\PycharmProjects\EyeTrackVR\EyeTrackApp
pyinstaller eyetrackapp.spec --noconfirm
cd C:\Users\beaul\OneDrive\Desktop
cd C:\Program Files (x86)\Inno Setup 6
ISCC C:\Users\beaul\OneDrive\Desktop\ETVR_SETUP.iss
cls
@echo off
color 0A
echo -------------------------------
echo ############ DONE #############
echo -------------------------------
PAUSE