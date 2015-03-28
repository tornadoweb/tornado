FROM python:2.7-onbuild

EXPOSE 8888

RUN apt-get update && apt-get install -y mysql-client

CMD python blog.py --mysql_host=mysql
