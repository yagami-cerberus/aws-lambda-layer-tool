#!/usr/bin/env python

from subprocess import Popen, PIPE
import configparser

from botocore.session import Session


PY37_BASE_DOCKERFILE = b'''
FROM ubuntu:18.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -y && apt-get install -y build-essential libssl-dev zlib1g-dev libncurses5-dev libncursesw5-dev libreadline-dev libsqlite3-dev libgdbm-dev libdb5.3-dev libbz2-dev libexpat1-dev liblzma-dev tk-dev libffi-dev curl zip

RUN curl https://www.python.org/ftp/python/3.7.3/Python-3.7.3.tar.xz -o Python-3.7.3.tar.xz && tar xf Python-3.7.3.tar.xz
RUN cd Python-3.7.3 && ./configure && make && make altinstall && cd .. && rm -rf Python-3.7.3 Python-3.7.3.tar.xz
RUN update-alternatives --install /usr/local/bin/python3 python3  /usr/local/bin/python3.7 1

RUN curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py && python3 get-pip.py
RUN pip3 install --upgrade pip setuptools botocore awscli
'''


PY_PKG_DOCKERFILE = '''
FROM %(base_image_name)s:latest

RUN mkdir /tmp/aws_lambda
RUN mkdir /tmp/aws_lambda/python
RUN pip3 install -t /tmp/aws_lambda/python %(packages)s
RUN cd /tmp/aws_lambda/python && python3 -c 'import os; print(",".join(sorted([dir[:-10] for dir in os.listdir("/tmp/aws_lambda/python") if dir.endswith(".dist-info")])))' > /tmp/package_list.txt && rm -rf bin *.dist-info
RUN cd /tmp/aws_lambda && zip -r /tmp/package.zip .

ARG AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
ARG AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
ARG AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN}
ARG RUNTIMES

RUN aws --region %(region)s lambda publish-layer-version --layer-name %(full_layer_name)s --zip-file fileb:///tmp/package.zip --compatible-runtimes ${RUNTIMES} --description `cat /tmp/package_list.txt`
'''


def main():
    docker_base_name = 'aws-py37-base'
    proc = Popen(('docker', 'build', '-t', docker_base_name, '-'), stdin=PIPE)
    proc.communicate(PY37_BASE_DOCKERFILE)
    if proc.returncode != 0:
        raise RuntimeError('Docker execution error')

    config = configparser.ConfigParser()
    config.read('packages.cfg')

    aws_options = config['aws']
    aws_region = aws_options['region']

    for layer_name, packages in config['packages'].items():
        sts_token = Session().create_client('sts').get_session_token()

        full_layer_name = 'py37_%s' % layer_name
        dockerfile = PY_PKG_DOCKERFILE % {'base_image_name': docker_base_name, 'packages': packages, 'region': aws_region, 'full_layer_name': full_layer_name}

        proc = Popen(('docker', 'build', '-t', 'aws-py37-%s' % layer_name,
                                '--build-arg', 'RUNTIMES=python3.7',
                                '--build-arg', 'AWS_ACCESS_KEY_ID=%s' % sts_token['Credentials']['AccessKeyId'],
                                '--build-arg', 'AWS_SECRET_ACCESS_KEY=%s' % sts_token['Credentials']['SecretAccessKey'],
                                '--build-arg', 'AWS_SESSION_TOKEN=%s' % sts_token['Credentials']['SessionToken'],
                                '-'), stdin=PIPE)
        proc.communicate(dockerfile.encode())

        if proc.returncode != 0:
            raise RuntimeError('Docker execution error')

if __name__ == '__main__':
    main()
