.DEFAULT_GOAL := run

install:
	poetry install

run:
	cd EyeTrackApp/ && poetry run python3 eyetrackapp.py

pyinstaller:
	poetry run pyinstaller eyetrackapp.spec EyeTrackApp/eyetrackapp.py

clean:
	rm eyetrack_settings.json
	rm EyeTrackApp/eyetrack_settings.json
	rm EyeTrackApp/eyetrack_settings.backup
	rm -rf EyeTrackApp/__pycache__/
	rm -rf EyeTrackApp/app/__pycache__/
	rm -rf EyeTrackApp/app/algorithms/__pycache__/
	rm -rf build/
	rm -rf dist/