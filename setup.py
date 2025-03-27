from setuptools import find_packages, setup

# Read the requirements from the requirements.txt file


def read_requirements():
    with open('requirements.txt') as f:
        return f.read().splitlines()


setup(
    name='waypanel',
    version='0.21.0',
    author='killown',
    author_email='systemofdown@gmail.com',
    description='A Wayfire panel that behaves like a shell',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/killown/waypanel',
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
    install_requires=read_requirements(),  # Reading from requirements.txt
    entry_points={
        'console_scripts': [
            'waypanel=waypanel.main:Panel',
        ],
    },
    packages=find_packages(),
    include_package_data=True,  # Include files specified in MANIFEST.in
)
