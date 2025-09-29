if __name__ == "__main__":
    try:
        import uvicorn
    except Exception as e:
        print('uvicorn is not available in this Python environment:', e)
        print('Try activating the project virtualenv (./.venv) before running Electron, or install uvicorn in the used Python.')
        raise
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
