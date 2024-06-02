import sys
import os
from PIL import Image, ImageDraw
import math
from random import randint

def replace_semi_transparent_pixels(path, tile_size, tile_size_y = False):
        tile_size_y = tile_size_y or tile_size
        tile_x = 95 * tile_size
        tile_y = 47 * tile_size_y
        mg_x = 18
        mg_y = 12

        no_margin = [
            'palisade', 'gate', 'stonewall', 'stonecorner','fortifiedwall','fortifiedcorner',
            'castle', 'krepost', 'donjon', 'towncenter', 'tower', 'outpost'
        ]
        # ['palisade', 'gate', 
        #           'palisade2_closed', 'palisade2_open',
        #           'stonewall', 'stonecorner','fortifiedwall','fortifiedcorner',
        #           'castle', 'krepost', 'donjon',
        #           'towncenter1', 'towncenter2', 'towncenter3', 'towncenter4', 
        #           'tower1', 'tower2', 'tower3', 'tower4', 'outpost']

        for b in no_margin:
            if b in path:
                mg_x = 1
                mg_y = 1
                break

        # Open the image
        image = Image.open(path).convert("RGBA")
        width, height = image.size
        pixels = image.load()

        #Starting crop margins
        top_crop = 0
        bottom_crop = height - 1
        left_crop = 0
        right_crop = width - 1

        # Find transparent rows to crop
        for y in range(height):
            if any(pixels[x, y][3] == 255 for x in range(width)):
                top_crop = y
                break
        for y in range(height - 1, top_crop, -1):
            if any(pixels[x, y][3] == 255 for x in range(width)):
                bottom_crop = y
                break

        # Find transparent columns to crop
        for x in range(width):
            if any(pixels[x, y][3] == 255 for y in range(height)):
                left_crop = x
                break

        for x in range(width - 1, left_crop, -1):
            if any(pixels[x, y][3] == 255 for y in range(height)):
                right_crop = x
                break

        # Perform cropping
        image = image.crop((left_crop, top_crop, right_crop + 1, bottom_crop + 1))
        width, height = image.size
        pixels = image.load()

        #replace_semi_transparent_pixels
        for y in range(height):
            for x in range(width):
                r, g, b, a = pixels[x, y]
                if a < 255 and a > 0: pixels[x, y] = (0, 0, 0, 0)
                elif r > 100 and g < 40  and b < 40  and g - b < 15 and g-b > -5 and g/r < 0.2: pixels[x, y] = (0, 0, 0, 0)

        #resize
        new_width = tile_x-mg_x
        if tile_size_y != tile_size: 
            image = image.resize((math.ceil(new_width*0.75), math.ceil(height*new_width*0.75/width) ))
        else:
            image = image.resize((new_width, math.ceil(height*new_width/width) ))
        width, height = image.size

        #Make background image
        new_height = math.ceil(height+mg_y/2)
        if new_height < tile_y: new_height = tile_y
        res_image = Image.new("RGBA", (tile_x, new_height), (255,0,255,255))
        res_width, res_height = res_image.size
        draw = ImageDraw.Draw(res_image)
        val_a = ( 0,  res_height-tile_y-1 )
        val_b = ( res_width/2, res_height-tile_y/2-1 )
        val_c = ( res_width, res_height-1 )
        if tile_size == tile_size_y:
            draw.polygon([(val_a[0], val_b[1]), (val_b[0], val_c[1]), (val_c[0], val_b[1]), (val_b[0], val_a[1])], fill=(0,0, 0,50), outline="black", width=1)
        else: #Esto es para 2x1
            p1 = (47, 0)
            p2 = (142, 94)
            p3 = (94, 142)
            p4 = (0, 47)
            draw.polygon([ p1, p2, p3, p4 ], fill=(0,0, 0,50), outline="black", width=1)
            # draw.polygon([(val_a[0], val_b[1]/2), (val_b[0]*1, val_c[1]), (val_c[0]*0.75, val_b[1]*0.75), (val_b[0]/2, val_a[1]/4)], fill=(0,0, 0,50), outline="black", width=1)
        # draw.point((val_a[0], val_b[1]), fill="black")
        # draw.point((val_b[0], val_c[1]), fill="black")
        # draw.point((val_c[0], val_b[1]), fill="black")
        # draw.point((val_b[0], val_a[1]), fill="black")

        #anchor en 47 - 73

        # Paste the image onto the new image
        res_image.paste(image, (math.ceil(mg_x/2), math.ceil(res_height-mg_y/2-height) ), image)

        #replace_semi_transparent_pixels
        pixels = res_image.load()
        
        for y in range(res_height):
            for x in range(res_width):
                r, g, b, a = pixels[x, y]
                if a < 255 and a > 0 and pixels[x, y] != (0,0,0,50): pixels[x, y] = (50,50, 50, 255)

        path = path.replace('/png/', '/res/')
        print(path.replace("C:/Users/javier/Desktop/res/",""), f'Anchor({int(tile_x/2)}, {int(res_height - tile_y/2)})')
        res_image.save(path)

        #d image -> Red, magenta, green and white picture.
        width, height = res_image.size
        pixels = res_image.load()
        for y in range(height):
            for x in range(width):
                r, g, b, a = pixels[x, y]

                if pixels[x, y] == (255,0,255,255): continue #magenta
                elif pixels[x, y] == (0,0, 0,50): pixels[x, y] = (255, 0, 0, 255) #red
                elif b > 100 and r/b <0.95 and g/b < 0.95 and  r-g > -6 and r-g < 6: pixels[x, y] = (0, 255, 0, 255) #green
                else: pixels[x, y] = (255, 255, 255, 255) #white
                
        path = path.replace('.png', 'd.png')
        res_image.save(path)

        #d_dmg image -> cyan, magenta, and black opacity
        width, height = res_image.size
        pixels = res_image.load()
        for y in range(height):
            for x in range(width):
                if pixels[x, y] == (255, 0, 255, 255): continue
                if pixels[x, y] ==  (255, 0, 0, 255): pixels[x, y] = (255, 0, 255, 255)
                else: pixels[x, y] = (0, 255, 255, 255)

        damage_layer =  Image.new('RGBA', (width, height), (0, 0, 0, 0))
        pixels = res_image.load()
        px_dmg = damage_layer.load()
        for i_dmg in range(4):
            for i in range(8):
                xy = [randint(2, width-2), randint(2, height-2)]
                while pixels[(xy[0], xy[1])] != (0,255,255,255): xy = [randint(2, width-2), randint(2, height-2)]
                px_dmg = paint_dmg(pixels, px_dmg, xy, i_dmg)        

        res_image.paste(damage_layer, (0, 0), damage_layer)
        path = path.replace('.png', '_dmg.png')
        res_image.save(path)

def paint_dmg(pixels, px_dmg, xy, i_dmg):
    for i in range(5):
        for x in range(5):
            px_dmg = paint_single_dmg_px(pixels, px_dmg, xy, i-3, x-3, i_dmg)
    return px_dmg

def paint_single_dmg_px(pixels, px_dmg, xy, x, y, i_dmg):
    x += xy[0]
    y += xy[1]
    try:
        if  pixels[(x,y)] == (0,255,255,255): px_dmg[(x,y)] = ( 0, 0, 0, 75 * i_dmg )
    except:
        print('error', x, y)
    return px_dmg

def modify_all_png():
    start_path = f'C:/Users/javier/Desktop/png/'
    for i in range(0,5):
        path = f'{start_path}{i+1}x{i+1}/'
        for filename in os.listdir(path):
            if filename.endswith(".png"): replace_semi_transparent_pixels(path + filename, i+1)
   
    #custom for 2X1
    path = f'{start_path}2x1/'
    for filename in os.listdir(path):
        if filename.endswith(".png"): replace_semi_transparent_pixels(path + filename, 2, 1)

if __name__ == "__main__":
    modify_all_png()