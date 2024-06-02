
def no_errors(error):
    if not error.no_error():
        try: 
            error.set( None )
        except:
            print('please no error')
            try: 
                error.set( None )
            except:
                print('please no error')

    return 'everything is fine'

print(no_errors)