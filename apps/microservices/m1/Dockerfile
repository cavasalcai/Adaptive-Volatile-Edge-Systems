FROM python:3

# set a directory for the app
WORKDIR /usr/bin/app

# copy all the files to the container
COPY . .

# install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# define the port number the container should expose
EXPOSE 5010

# run the command
CMD ["python", "./m1.py"]