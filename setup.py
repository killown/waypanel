from setuptools import setup
from setuptools.command.install import install as _install
import subprocess
import os

class InstallWithPostInstall(_install):
    def run(self):
        # Run the standard install process
        _install.run(self)
        # Run the custom post-install script
        self.run_post_install()

    def run_post_install(self):
        # Define the path to the post-install script
        script_path = os.path.join(os.path.dirname(__file__), 'post_install.sh')
        
        # Ensure the script is executable
        if not os.access(script_path, os.X_OK):
            print(f"Making script {script_path} executable.")
            os.chmod(script_path, 0o755)
        
        # Execute the post-install script
        print(f"Running post-install script: {script_path}")
        subprocess.check_call(['sh', script_path])

setup(
    name='waypanel',
    version='0.1.0',
    author='killown',
    author_email='systemofdown@gmail.com',
    description='A Wayfire panel that behaves like a shell',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/killown/waypanel',
    cmdclass={
        'install': InstallWithPostInstall,
    },
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

