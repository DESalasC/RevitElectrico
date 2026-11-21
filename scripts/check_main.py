with open(r'D:\Work\PROJECTS\RevitElectrico\scripts\RE6_COLOCAR_TODOS_v01.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Check if main() is called
if 'if __name__ == "__main__":' in content:
    print('Has main guard')
    idx = content.find('if __name__ == "__main__":')
    print(content[idx:idx+100])
else:
    print('NO main guard - script does nothing when exec()d')
    # Check end of file
    print('--- END OF FILE ---')
    print(content[-300:])