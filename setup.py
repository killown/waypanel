from setuptools import setup

setup(
    name='waypanel',
    version='0.8.2',
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
    install_requires=[
        # List your project dependencies here.
    ],
    entry_points={
        'console_scripts': [
            'waypanel=waypanel.main:Panel',
        ],
    },
)

