from setuptools import setup


setup(
    name='PyChromecast',
    version='0.3.2',
    license='MIT',
    url='https://github.com/balloob/pychromecast',
    author='Paulus Schoutsen',
    author_email='paulus@paulusschoutsen.nl',
    description='Python module to talk to Google Chromecast.',
    packages=['pychromecast'],
    zip_safe=False,
    include_package_data=True,
    platforms='any',
    install_requires=['requests', 'ws4py'],
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ]
)
