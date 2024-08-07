import setuptools

setuptools.setup(
    name='RLutils',
    version='0.0.1',
    author='Davide Domini, Nicolas Farabegoli, Gianluca Aguzzi',
    description='RL utils',
    long_description='RL utils - TAAS 2024 Experiments - Edge-Cloud Intelligence',
    long_description_content_type='text/markdown',
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],  # Information to filter the project on PyPi website
    python_requires='>=3.6',  # Minimum version requirement of the package
    py_modules=["RLutils"],  # Name of the python package
    package_dir={'': 'src'},  # Directory of the source code of the package
    install_requires=["torch"]  # Install other dependencies if any
)