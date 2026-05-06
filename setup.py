#!/usr/bin/env python3
"""
Setup configuration for ForestGump: Hermes-compatible bare-metal pentesting agent.

Installation:
  pip install -e .

Then use:
  forestgump chat "your task"
  forestgump model --list
  forestgump skills --search "pattern"
  forestgump memory --list
  forestgump sessions --list
"""

from setuptools import setup, find_packages
from pathlib import Path

here = Path(__file__).parent.resolve()
long_description = (here / 'README.md').read_text(encoding='utf-8') if (here / 'README.md').exists() else ''

setup(
    name='forestgump',
    version='0.2.0',
    description='Bare-metal AI pentesting agent with Hermes-compatible interface',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='ForestGump Team',
    license='MIT',
    py_modules=[
        'agent',
        'cli',
        'menu',
        'skills',
        'skill_manager',
        'memory_manager',
        'theme',
    ],
    install_requires=[
        'requests>=2.28.0',
        'anthropic>=0.7.0',
    ],
    extras_require={
        'dev': [
            'pytest>=7.0',
            'black>=22.0',
            'flake8>=4.0',
        ],
        'ollama': [
            'ollama>=0.1.0',
        ],
        'rich': [
            'rich>=13.0',  # For enhanced terminal UI
        ],
    },
    entry_points={
        'console_scripts': [
            'forestgump=cli:main',
        ],
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Topic :: System :: Shells',
        'Topic :: Security :: Penetration Testing',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS',
    ],
    python_requires='>=3.9',
    keywords='pentesting security agent llm ai bare-metal hermes',
    project_urls={
        'Documentation': 'https://github.com/anthropics/claude-code',
        'Source': 'https://github.com/anthropics/claude-code',
        'Tracker': 'https://github.com/anthropics/claude-code/issues',
    },
)
