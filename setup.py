from setuptools import setup, find_packages
import os

from dsw_tdk import __app__, __version__

this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = ''.join(f.readlines())

setup(
    name=__app__,
    version=__version__,
    keywords='dsw template toolkit',
    description='Data Stewardship Wizard Template Development Toolkit',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Marek Suchánek',
    author_email='marek.suchanek@ds-wizard.org',
    license='Apache-2.0',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'dsw-tdk = dsw_tdk:main',
        ]
    },
    install_requires=[
        'aiohttp',
        'click',
        'colorama',
        'humanize',
        'Jinja2',
        'python-dotenv',
        'python-slugify',
        'watchgod',
    ],
    classifiers=[
        'Framework :: AsyncIO',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Topic :: Internet :: WWW/HTTP :: HTTP Servers',
        'Topic :: Internet :: WWW/HTTP :: Indexing/Search',
    ],
)
