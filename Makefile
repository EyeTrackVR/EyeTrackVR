.DEFAULT_GOAL := run

install:
	poetry install

run:
	cd EyeTrackApp/ && poetry run python eyetrackapp.py

pyinstaller:
	poetry run pyinstaller EyeTrackApp/eyetrackapp.spec EyeTrackApp/eyetrackapp.py

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf EyeTrackApp/__pycache__/
	rm -rf EyeTrackApp/app/__pycache__/
	rm -rf EyeTrackApp/app/algorithms/__pycache__/
	rm EyeTrackApp/eyetrack_settings.backup
	rm EyeTrackApp/eyetrack_settings.json