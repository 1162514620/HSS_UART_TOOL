from setuptools import setup, find_packages

setup(
    name="multiserial-tool",
    version="1.0.0",
    description="多功能串口助手 - MultiSerial Tool",
    author="",
    author_email="",
    packages=find_packages(),
    include_package_data=True,
    python_requires=">=3.7",
    install_requires=[
        "pyserial>=3.5",
        "matplotlib>=3.7.0",
        "numpy>=1.25.0",
        "chardet>=5.0.0",
    ],
    entry_points={
        "console_scripts": [
            "multiserial-tool=main:main"
        ]
    }
)
