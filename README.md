

<p align="center">
  <br />
  <img src="https://i.imgur.com/tCGf9Js.png" height="200">
</p>
  
## NavBoat
A quick service control widget for mac os navbar.  
Transform your cli services into a YAML config file and run them in 2 clicks!  
  
<img src="https://i.imgur.com/mEsVQQS.png" height="300">

### Features
- Supports background services
- Shows open ports for running services, click on a host opens a browser tab
- Can show status and phisical memory, of a process, including its spawned subprocesses.
- Supports virtual environments
- Supports environment variables
- Supports service autorun
- Supports nested categories
- Fully shuts down all processes on exit
- Supports additional actions (like updating or building)

### Setup
`pip install rumps psutil PyYAML`
`python src/app.py`

### Project status
Proof-of-concept, needs refactoring. 
Config syntax may change. Errors in third-party services are not reported.
Framework limitations allow to update the widget only when it is not open.
It is partially updated every 5 seconds with a full refresh every minute.

### Syntax
```YAML
# required
    - name: action name
      type: subprocess # only subprocess is supported right now
      background: bool # is this a service or a single-run script
      dir: /path/to/working/directory/of/the/service # where is the target dir located
      command: ./server # what to run
      arguments: -ngl 1 # cli arguments
# optional
      env: # a list of enviromnet variables, add _clean to clear existing env.variables
      venv: # path to python venv activation file.
      wait_for: word # change service status to running only when a word is found in stdout (or on timeout). Stderr and sub-process stdout is not supported.
      shell: bool # use this to run cli commands if regular mode does not work, in this case all commands should be passed in "command" and "arguments" should be empty (TODO: fix).
      window: bool # open terminal window.
      autorun: bool # run the service when this app is started.
      subactions: # a list of extra actions to run
        - name: Update #subaction name
          when: stopped # when to show the action (update & rebuild only whe the service is running, make api calls when it is running)
          window: true # open terminal window
          command: | # list of commands to run, will be concatinated with `&&`
            git pull
            make clean
            env -i make
            exit
```

### Improvement ideas:
- cron-like services
- profiles for various arguments
- auto-file-dir argument, selecting a file from directory and passing it as an argument (useful for LLM files)
- sub-action status
  
### Special thanks
This project is heavily based on [RUMPS](https://github.com/jaredks/rumps) widget framework.
  
### License
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)