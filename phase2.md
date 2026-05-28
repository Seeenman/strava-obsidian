# Phase 2
In this repository is a python script that can make calls to the Strava API to get data from my recent activities. Your job is to do the following:
## change the activities that get pulled
- Make it so that instead of defaulting to pulling data from the 30 most recent activities it
  - defaults to pulling data from all activities that occurred on the current date
  - if a date is specified pull data from all activities that occurred on that date
  - only pulls data for run and bicycle activities 
## where pulled data is stored
- The data that is retrieved should be stored in a markdown file named according to the following scheme: `log-<year>-<month>-<day>-<dayofweek>.md`
    - for example, the provided file `log-2026-05-27-Wed.md` would correspond to data pulled for Wednesday May 27th 2026.
- If a markdown file with this name does not already exist, create it and copy the contents of `log-template.md` to the newly created file.
- If a markdown file with this name already exists do not recreate it.
## how the pulled data is stored in the markdown file
- Assuming the markdown file for a given day's activities already exists
	- If the activity was a running activity then put the data under the `# Run` section. If it was a biking activity then put the data under the `# Bike` section. The do the following.
	- replace the [time of day] text with the time of day the activity was started
	- put the distance (in miles) of the activity directly after the ruler emoji
	- put the amount of time the activity took directly after the timer emoji
		- The format should be hh:mm:ss for activities over one hour
		- the format should be mm:ss for activities under one hour
	- put the elevation gain (in feet) directly after the mountain emoji
	- Put the average heart rate directly after the ↔️❤️ emojis
	- put the max heart rate directly after the ⬆️❤ emojis
  - There is an example of how this should look in `log-2026-05-27-Wed.md`
## other things
- I should be able to run the script from the command line. This can be achieved by creating a shell script wrapper for the python script.
- I should be able to specify, as a command line argument, the path to the directory where I want the markdown file that has the data to exist (the file may even already exist in this directory).
