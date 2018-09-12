import pandas as pd
import requests
import os
import ast
import geopandas 
from shapely.geometry import Point, Polygon
import matplotlib.pyplot as plt

##############
## OVERPASS ##
##############

def generate_overpass_query(tags, objects,
                            osm_bbox,
                            entity="building"):
    """
    Generate and return Overpass query string
 
    Args:
     tags: list of tags (e.g. 'fuel')
     objects: list of objects (e.g. nodes, ways)
     osm_bbox: vertex list of OSM bounding box convention. Order is: (S, W, N, E)
     entity: querying entity type (amenity by default)
    
    Returns:
     compactOverpassQLstring: query string
    """

    compactOverpassQLstring = '[out:json][timeout:60];('
    for tag in tags:
        for obj in objects:
            compactOverpassQLstring += '%s["%s" ~ "%s"](%s,%s,%s,%s);' % (obj, entity, tag,
                                                                        osm_bbox[0],
                                                                        osm_bbox[1],
                                                                        osm_bbox[2],
                                                                        osm_bbox[3])
    compactOverpassQLstring += ');out body;>;out skel qt;'    
    return compactOverpassQLstring

    
def get_osm_data(compactOverpassQLstring, osm_bbox, osm_objects):
    """
    Get Data from OSM via Overpass. Convert JSON to Pandas dataframe. Save.
    If data has been downloaded previously, read from csv

    Args:
     compactOverpassQLstring: Query string
     osm_bbox: OSM-spec'd bounding box as list  
     osm_objects: OSM objects requested

    Returns:
     osmdf: pandas dataframe of extracted JSON 
    """

    # Filename
    bbox_string = '_'.join([str(x) for x in osm_bbox])
    osm_object_string = '_'.join([str(x) for x in osm_objects])

    osm_filename = 'data/osm_data_{}_osm_objects_{}.csv'.format(bbox_string,
                                                                osm_object_string)

    if os.path.isfile(osm_filename):
        osm_df = pd.read_csv(osm_filename)

    else:
        # Request data from Overpass
        osmrequest = {'data': compactOverpassQLstring}
        osmurl = 'http://overpass-api.de/api/interpreter'

        # Ask the API
        osm = requests.get(osmurl, params=osmrequest)
        # print osm.url
        
        # Convert the results to JSON and get the requested data from the 'elements' key
        # The other keys in osm.json() are metadata guff like 'generator', 'version' of API etc. 
        osmdata = osm.json()
        osmdata = osmdata['elements']
        # Convert JSON output to pandas dataframe
        for dct in osmdata:
            if dct.has_key('tags'):
                for key, val in dct['tags'].iteritems():
                    dct[key] = val
                del dct['tags']
            else:
                pass
        osm_df = pd.DataFrame(osmdata)

        # Weird truncation with long ways. Getting ',...]' at the end!
        # Removing csv write until I can fix this. 
        # osm_df.to_csv(osm_filename, header=True, index=False, encoding='utf-8')
        
    return osm_df




def convert_list_string(list_string):
    """
    Converts a string list to a list of strings
    u'[a, b, b]' --> ['a', 'b', 'c']
    Needed to expand the nodes columns in ways 
    """
    list_unicode_string =  unicode(list_string, "utf-8")
    return ast.literal_eval(list_unicode_string)


###############################
## GEOPANDAS TRANSFORMATIONS ##
###############################

def extend_ways_to_node_view(osmdf):
    """
    """
    
    osmdf_ways = osmdf.query('type == "way"')[['id', 'nodes', 'type']]
    osmdf_nodes = osmdf.query('type == "node"')[['id', 'lat', 'lon']]
    osmdf_ways['nodes'] = osmdf_ways['nodes'].astype(str)
    osmdf_ways['nodes'] = osmdf_ways['nodes'].apply(convert_list_string)
    
    osmdf_ways_clean = (osmdf_ways
                        .set_index(['id', 'type'])['nodes']
                        .apply(pd.Series)
                        .stack()
                        .reset_index())

    osmdf_ways_clean.columns = ['way_id', 'type', 'sample_num', 'nodes']
    # osmdf_nodes['id'] = osmdf_nodes['id'].astype(str)
    # osmdf_ways_clean['nodes'] = osmdf_ways_clean['nodes'].astype(str) 
    
    osmdf_clean = pd.merge(osmdf_ways_clean,
                           osmdf_nodes,
                           left_on='nodes',
                           right_on='id').drop(['nodes'], axis=1)
    return osmdf_clean
    

def coords_df_to_geopandas_points(osmdf, crs={'init': u'epsg:4167'}):
    """
    """
    
    osmdf['Coordinates'] = list(zip(osmdf.lon, osmdf.lat))
    osmdf['Coordinates'] = osmdf['Coordinates'].apply(Point)
    points_osmdf_clean = geopandas.GeoDataFrame(osmdf, geometry='Coordinates', crs=crs)
    return points_osmdf_clean


def geopandas_points_to_poly(points_df, crs={'init': u'epsg:4167'}):
    """
    """
    
    points_df['geometry'] = points_df['Coordinates'].apply(lambda x: x.coords[0])
    poly_osmdf_clean = (points_df
                        .groupby('way_id')['geometry']
                        .apply(lambda x: Polygon(x.tolist()))
                        .reset_index())
    poly_osmdf_clean = geopandas.GeoDataFrame(poly_osmdf_clean, crs=crs)
    return poly_osmdf_clean


##############
## PLOTTING ##
##############

def plot_unit_residential(res_df, unit_df,
                          name,  boundary_column ='AU2013_V1_00_NAME'): 
    """
    Plot OSM residential area polygons and StatsNZ boundaries
    on shared X and Y axes for comparison of boundary limits.
    """
    
    f, ax = plt.subplots(2, sharex=True, sharey=True,figsize=(10, 6))
    res = res_df[res_df[boundary_column] == name].reset_index()
    res.plot(ax=ax[0])

    stat_unit = unit_df[unit_df[boundary_column] == name].reset_index()
    stat_unit.plot(ax=ax[1])
    return


###############
## NOMINATIM ##
###############

def reverse_geo_code(osm_type="W", osm_id="48029394"):
    """
    Function for reverse geocoding with Nominatim
    
    Args:
     osm_type: Either 'W' or 'N' for way or node
     osm_idf: OSM ID. 'id' key from Overpass output
    
    Returns:
     df: 
    """
    
    query = "osm_type={}&osm_id={}&format=json".format(osm_type, osm_id)
    nomrequest = {'data': query}
    nomurl = 'https://nominatim.openstreetmap.org/reverse?'

    # Ask the API
    url = nomurl+query
    nom_res = requests.get(nomurl, params=query)
    json_data = json.loads(nom_res.text)
    centre_coords = pd.DataFrame({'osm_id': [osm_id],
                                  'lat': [json_data['lat'] if json_data.has_key('lat') else 'NA'], 
                                  'lon': [json_data['lon'] if json_data.has_key('lon') else 'NA']})
    return centre_coords
