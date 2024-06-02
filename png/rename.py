import os
import sys
import shutil

#dark age es como una nueva civi

def for_area(s:str):
    areas = [
        'west',
        'medi',
        'meso',
        'slav',
        'seas',
        'orie',
        'indi',
        'east',
        'ceas',
        'asia',
        'afri'
    ]
    res = []
    for a in areas:
        res.append('b_'+a+'_'+s)
    return res

def for_more_area(s:str):
    areas = [
        'geor',
        'arme',
        'west',
        'medi',
        'meso',
        'burg',
        'pole',
        'indi',
        'hind',
        'beng',
        'east',
        'asia',
        'ceas',
        'bohe',
        'afri',
        'slav',
        'sici',
        'roma',
        'seas',
        'orie',
        'gurj'
    ]
    res = []
    for a in areas:
        res.append('b_'+a+'_'+s)
    return res

def rename_and_move_file(file):
    renames = {
        'berry':['n_forage_bush_x1','n_forage_fruit_x1'],
        'berry33':['n_forage_bush_33_x1','n_forage_fruit_33_x1'],
        'berry66':['n_forage_bush_66_x1','n_forage_fruit_66_x1'],
        'tree':[
            'n_tree_acacia_x1',
            'n_tree_autumn_oak_x1',
            'n_tree_bamboo_x1',
            'n_tree_birch_x1',
            'n_tree_bush_a_x1',
            'n_tree_bush_b_x1',
            'n_tree_bush_c_x1',
            'n_tree_cypress_x1',
            'n_tree_dead_x1',
            'n_tree_dragon_x1',
            'n_tree_italian_pine_x1',
            'n_tree_jungle_x1',
            'n_tree_mangrove_x1',
            'n_tree_oak_x1',
            'n_tree_olive_x1',
            'n_tree_palm_x1',
            'n_tree_pine_x1',
            'n_tree_rainforest_x1',
            'n_tree_reeds_x1',
            'n_tree_scenario_a_x1',
            'n_tree_scenario_b_x1',
            'n_tree_scenario_c_x1',
            'n_tree_scenario_d_x1',
            'n_tree_scenario_e_x1',
            'n_tree_scenario_f_x1',
            'n_tree_scenario_g_x1',
            'n_tree_scenario_h_x1',
            'n_tree_scenario_i_x1',
            'n_tree_scenario_j_x1',
            'n_tree_scenario_k_x1',
            'n_tree_scenario_l_x1',
            'n_tree_snow_autumn_oak_x1',
            'n_tree_snow_pine_x1'     
        ],
        'tree_big':['n_tree_baobab_x1'],
        'tree_cut':['n_tree_felled_generic_x1','n_tree_felled_baobab_x1','n_tree_felled_bamboo_x1'],
        'gold':['n_mine_gold_x1'],
        'gold66':['n_mine_gold_66_x1'],
        'gold33':['n_mine_gold_33_x1'],
        'stone':['n_mine_stone_x1'],
        'stone66':['n_mine_stone_66_x1'],
        'stone33':['n_mine_stone_33_x1'],
        'housef':[ 'b_misc_foundation_house_x1' ], #3 steps go here
        'house1':[ 'b_dark_house_age1_x1' ],
        'house2':{ 'areas':['house_age2_x1'] },
        'house3':{ 'areas':['house_age3_x1'] },
        'mining':{ 'areas':['mining_camp_age2_x1'] },
        'miningf':['b_misc_foundation_mining_camp_x1'], #3 steps go here
        'mill1':['b_dark_mill_age1_x1'],
        'mill2':{ 'areas':['mill_age2_x1'] },
        'mill3':{ 'areas':['mill_age3_x1'] },
        'mill1d':['b_dark_mill_age1_destruction_x1'],
        'mill2d':{ 'areas':['mill_age2_destruction_x1'] },
        'mill3d':{ 'areas':['mill_age3_destruction_x1'] },
        'millf':['b_misc_foundation_mill_x1'], #3 steps go here
        'lumber':{ 'areas':['lumber_camp_age2_x1'] },
        'lumberf':['b_misc_foundation_lumber_camp_x1'], #3 steps go here
        'palisade':['b_dark_wall_palisade_x1'],
        'palisade2_closed':['b_dark_gate_palisade_e_closed_x1'],
        'palisade2_open':['b_dark_gate_palisade_e_open_x1'],
        'palisade22_closed':['b_dark_gate_palisade_n_closed_x1'],
        'palisade22_open':['b_dark_gate_palisade_n_open_x1'],
        'stonewall':{'areas':['wall_stone_x1']},
        'stonewallf':{'areas':['wall_stone_constr_x1']},
        'fortifiedwall':{'areas':['wall_fortified_x1']},
        'stonecorner':{'areas':['gate_stone_corner_x1']},
        'fortifiedcorner':{'areas':['gate_fortified_corner_x1']},
        'stone2_closed':{'areas':['gate_stone_e_closed_x1', 'gate_fortified_e_closed_x1']},
        'stone2_open':{'areas':['gate_stone_e_open_x1', 'gate_fortified_e_open_x1']},
        'stone22_closed':{'areas':['gate_stone_n_closed_x1', 'gate_fortified_n_closed_x1']},
        'stone22_open':{'areas':['gate_stone_n_open_x1', 'gate_fortified_n_open_x1']},
        'palisade_flag':['b_dark_wall_palisade_flag_x1', 'b_dark_gate_palisade_flag_x1'],
        'outpost':['b_dark_outpost_age1_x1'],
        'palisade_gate_corner':['b_dark_gate_palisade_corner_x1'],
        'barracksf':['b_misc_foundation_barracks_x1'],
        'barracks':['b_dark_barracks_age1_x1'],
        'barracks2':{'areas':['barracks_age2_x1']},
        'barracks3':{'areas':['barracks_age3_x1']},
        'barracks1d':['b_dark_barracks_age1_destruction_x1'],
        'barracks2d':{'areas':['barracks_age2_destruction_x1']},
        'barracks3d':{'areas':['barracks_age3_destruction_x1']},
        'blacksmithf':['b_misc_foundation_blacksmith_x1'],
        'blacksmith2d':{'areas':['blacksmith_age2_destruction_x1']},
        'blacksmith3d':{'areas':['blacksmith_age3_destruction_x1']},
        'blacksmith2':{'areas':['blacksmith_age2_x1']},
        'blacksmith3':{'areas':['blacksmith_age3_x1']},
        'archeryf':['b_misc_foundation_archery_range_x1'],
        'archery2':{'areas':['archery_range_age2_x1']},
        'archery2d':{'areas':['archery_range_age2_destruction_x1']},
        'archery3':{'areas':['archery_range_age3_x1']},
        'archery3d':{'areas':['archery_range_age3_destruction_x1']},
        'stable2':{'areas':['stable_age2_x1']},
        'stable3':{'areas':['stable_age3_x1']},
        'stablef':['b_misc_foundation_stable_2_x1', 'b_misc_foundation_stable_1_x1' ],
        'siege':{'areas':['siege_workshop_age3_x1']},
        'monastery':{'areas':['monastery_age3_x1']},
        'monasteryf':['b_misc_foundation_monastery_x1'],
        'market2':{'areas':['market_age2_x1']},
        'market3':{'areas':['market_age3_x1', 'market_age4_x1' ]},
        'marketf':['b_misc_foundation_market_x1'],
        'market2d':{'areas':['market_age2_destruction_x1']},
        'market3d':{'areas':['market_age3_destruction_x1', 'market_age4_destruction_x1']},
        'castle':{'more_areas':['castle_age3_x1' ]},
        'castled':{'more_areas':['castle_age3_destruction_x1' ]},
        'castlef':['b_misc_foundation_castle_x1' ],
        'university':{'areas':['university_age3_x1', 'university_age4_x1' ]},
        'universityf':['b_misc_foundation_university_1_x1', 'b_misc_foundation_university_2_x1'],
        'towncenter1':['b_dark_town_center_age1_main_x1', 'b_dark_town_center_age1_x1'],
        'towncenter2':{'areas':['town_center_age2_main_x1', 'town_center_age2_x1']},
        'towncenter3':{'areas':['town_center_age3_main_x1', 'town_center_age3_x1']},
        'towncenter4':{'areas':['town_center_age4_main_x1', 'town_center_age4_x1']},
        'towncenterf':['b_misc_foundation_town_center_x1'],
        'tower1':{'areas':['tower_age2_x1']},
        'tower2':{'areas':['tower_age3_x1']},
        'tower3':{'areas':['tower_age4_x1']},
        'tower4':{'areas':['tower_bombard_x1']},
        'dock1':['b_dark_dock_age1_x1'],
        'dock2':{'areas':['dock_age2_x1']},
        'dock3':{'areas':['dock_age3_x1']},
        'dock4':{'areas':['dock_age4_x1']},
        'dock1d':['b_dark_dock_age1_destruction_x1'],
        'dock2d':{'areas':['dock_age2_destruction_x1']},
        'dock3d':{'areas':['dock_age3_destruction_x1', 'dock_age4_destruction_x1']},
        'dockf':['b_misc_foundation_dock_x1'],
        'fortified_church':['b_medi_fortified_church_x1'],
        'caravanserai':['b_indi_caravanserai_age4_x1'],
        'feitoria':['b_medi_feitoria_x1'],
        'feitoriad':['b_medi_feitoria_destruction_x1'],
        'krepost':['b_slav_krepost_x1','b_slav_krepost_age3_x1'],
        'donjon':['b_medi_donjon_x1'],
        'donjonf':['b_misc_foundation_donjon_x1'],
        'donjond':['b_medi_donjon_destruction_x1'],
        'folwark1':['b_dark_folwark_age1_x1'],
        'folwark2':['b_slav_folwark_age2_x1'],
        'folwark3':['b_slav_folwark_age3_x1'],
        'empty':['b_west_gate_stone_flag_x1','b_west_fortified_stone_flag_x1',
            'b_dark_town_center_age1_front_x1', 'b_dark_town_center_age1_center_x1','b_dark_town_center_age1_back_x1',
                 'b_misc_snow_1_x1', 'b_misc_snow_2_x1', 'b_misc_snow_3_x1', 'b_misc_snow_4_x1', 'b_misc_snow_5_x1', 'b_misc_snow_6_x1', 'b_misc_snow_7_x1', 'b_misc_snow_8_x1', 'b_misc_snow_9_x1', 'b_misc_snow_10_x1',],
        'empty2':{'areas':['town_center_age2_front_x1', 'town_center_age2_center_x1','town_center_age2_back_x1', 'town_center_age2_shadow_x1',
                          'town_center_age3_front_x1', 'town_center_age3_center_x1','town_center_age3_back_x1', 'town_center_age3_shadow_x1',
                          'town_center_age4_front_x1', 'town_center_age4_center_x1','town_center_age4_back_x1', 'town_center_age4_shadow_x1',
                          ]}
    }

    mod = 'Power - Checker buildings'
    source_path = f'C:/Users/javier/Desktop/{file}.smx'
    if not os.path.isfile(source_path):
        print(f"Error: The file '{source_path}' does not exist.")
        return

    if renames.get(file) == None: 
        print(f'File not found: {file}')
        return
    
    new_names = renames[file]
    if type(new_names) == dict: 
        res = []

        strs = new_names.get('areas')
        if strs != None:
            for s in strs: res += for_area(s)
        
        strs = new_names.get('more_areas')
        if strs != None:
            for s in strs: res += for_more_area(s)

        new_names = res


    for fname in new_names:
        destination_path = f'C:/Users/javier/Games/Age of Empires 2 DE/76561198074571609/mods/local/{mod}/resources/_common/drs/graphics/{fname}.smx'

        try:
            shutil.copyfile(source_path, destination_path)
            print(f"File '{source_path}' duplicated as '{destination_path}' successfully.")
        except OSError as e:
            print(f"Error: Failed to duplicate the file '{source_path}': {e}")



if __name__ == '__main__':
    # Check if the correct number of command-line arguments is provided
    if len(sys.argv) != 2:
        print("Usage: python rename_and_move.py <source_file_path> <destination_file_path>")
    else:
        rename_and_move_file(sys.argv[1])
