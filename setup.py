from setuptools import setup, find_packages


setup(
    name='PyChromecast',
    version='0.6.13',
    license='MIT',
    url='https://github.com/balloob/pychromecast',
    author='Paulus Schoutsen',
    author_email='paulus@paulusschoutsen.nl',
    description='Python module to talk to Google Chromecast.',
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    platforms='any',
    install_requires=['requests>=2.0', 'protobuf>=3.0.0b1.post2', 'zeroconf>=0.16.0'],
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
