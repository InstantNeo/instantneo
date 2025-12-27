from setuptools import setup, find_packages

setup(
    name='instantneo',
    version='0.2.0',
    packages=find_packages(),
    install_requires=[
        'docstring_parser',
        'httpx',
        'cryptography',
    ],
    author='Diego Ponce de León Franco',
    author_email='dponcedeleonf@gmail.com',
    description='Framework para construir agentes con LLMs, con control granular y composición simple.',
    long_description=open('README.md', encoding='utf-8').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/instantneo/instantneo',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.11',
    ],
    keywords='llm, agents, ai, openai, anthropic, groq, gemini, vertex ai',
    project_urls={
        'Bug Reports': 'https://github.com/instantneo/instantneo/issues',
        'Source': 'https://github.com/instantneo/instantneo',
    },
)