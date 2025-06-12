from setuptools import setup

setup(
    name="sip-watcher",
    version="1.0.0",
    py_modules=["sip_watcher"],
    entry_points={
        "console_scripts": [
            "sip-watcher=sip_watcher:main",
        ]
    },
)
