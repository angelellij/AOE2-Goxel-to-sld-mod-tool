import os
import sys
import shutil

def print_dir():
    mod = 'Power - Checker resources'
    path = f'C:/Users/javier/Games/Age of Empires 2 DE/76561198074571609/mods/local/{mod}/resources/_common/drs/graphics'

    for filename in os.listdir(path):
        print(filename)

if __name__ == '__main__':
    print_dir()

