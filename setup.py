from setuptools import setup, find_packages
import sys

# Detectar si es una instalación sin extras especificados
is_direct_install = "install" in sys.argv and not any(arg.startswith("instantneo[") for arg in sys.argv)
print(f"Instalación: {sys.argv}")
# Dependencias base
base_requires = ['docstring_parser']

# Si es una instalación directa sin extras, agregar todas las dependencias
install_requires = base_requires.copy()
if is_direct_install:
    # print("\nAtención: Instalando instantneo con todas las dependencias.\n"
    #       "Para una instalación más ligera, especifica: pip install instantneo[openai], "
    #       "instantneo[anthropic], o instantneo[groq]\n")
    install_requires.extend(['openai', 'anthropic', 'groq'])

setup(
    name='instantneo',
    version='0.1.2', 
    packages=find_packages(),
    install_requires=install_requires,
    extras_require={
        'openai': ['openai'],
        'anthropic': ['anthropic'],
        'groq': ['groq'],
        'all': ['openai', 'anthropic', 'groq']
    },
    author='Diego Ponce de León Franco',
    author_email='dponcedeleonf@gmail.com',
    description='',
    long_description=open('README.md', encoding='utf-8').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/dponcedeleonf/instantneo',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.11',
    ],
    keywords='openai, agent, wrapper',
    project_urls={
        'Bug Reports': 'https://github.com/dponcedeleonf/instantneo/issues',
        'Source': 'https://github.com/dponcedeleonf/instantneo',
    },
)