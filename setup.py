from setuptools import setup, find_packages


long_description = open('README.rst').read()

setup(
    name='PyChromecast',
    version='0.7.5',
    license='MIT',
    url='https://github.com/balloob/pychromecast',
    author='Paulus Schoutsen',
    author_email='paulus@paulusschoutsen.nl',
    description='Python module to talk to Google Chromecast.',
    long_description=long_description,
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    platforms='any',
    install_requires=list(val.strip() for val in open('requirements.txt')),
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ]
)
