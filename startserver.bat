@echo off

:: Run the custom management command
python manage.py check_admin || goto :EOF

:: Start the Django development server
python manage.py runserver
