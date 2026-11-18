"""Kept so `python backend.py` still works. The app lives in the app/ package: python -m app"""
import runpy

if __name__ == '__main__':
    runpy.run_module('app', run_name='__main__')
