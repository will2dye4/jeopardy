from setuptools import find_packages, setup


with open('requirements.txt') as f:
    requirements = f.readlines()


setup(
    name='jeopardy',
    version='0.5.0',
    packages=find_packages(),
    install_requires=requirements,
    python_requires='~=3.7',
    entry_points={
        'console_scripts': [
            'jeopardy = jeopardy.main:main',
            'jeopardyd = jeopardy.server:main',
        ]
    }
)
