from setuptools import find_packages, setup


def read_requirements():
    with open("requirements.txt") as f:
        return f.read().splitlines()


setup(
    name="waypanel",
    version="0.9.5",
    author="killown",
    author_email="systemofdown@gmail.com",
    description="A Wayfire panel that behaves like a shell",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/killown/waypanel",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.12",
    install_requires=read_requirements(),
    extras_require={
        "dev": [
            "pygobject-stubs[Gtk4,Gdk]",
        ],
    },
    scripts=["scripts/waypanel"],
    packages=find_packages(),
    include_package_data=True,
)
