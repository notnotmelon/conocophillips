from multiprocessing import Pool
import parse_schemas
import folium
from folium import *
import webbrowser
from folium.plugins import *
import json
import pandas as pd
import re
import countryflag
import pycountry
import time
from functools import lru_cache

continents = ['Low-income countries', 'High-income countries', 'Lower-middle-income countries', 'Upper-middle-income countries', 'World', 'Africa', 'Asia', 'Europe', 'North America', 'Oceania', 'South America']

def create_map_2(df, year, primary_key, gradient):
    current_time_ms = int(time.time() * 1000)
    if 'year' in df.columns:
        df = df[(df['year'] == year)]
    elif 'Year' in df.columns:
        df = df[(df['Year'] == year)]
    else:
        raise ValueError('Year column not found')
    
    if 'Country' in df.columns:
        df = df[~df['Country'].isin(continents)]
        df = df[~df['Country'].apply(lambda x: x if re.match('^.*\([A-Z]+\).*$', x) else None).notna()]

    value_dict = {}

    if primary_key in df.columns:
        df[primary_key] = df[primary_key].astype(float)  # Convert values to float
        min_value = df[primary_key].min()
        max_value = df[primary_key].max()
    else:
        min_value = 0
        max_value = 0
    print(min_value, max_value)

    tile_layer = folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
        attr='Tiles &copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ, USGS, Intermap, iPC, NRCAN, Esri Japan, METI, Esri China (Hong Kong), Esri (Thailand), TomTom, 2012',
        min_zoom=3,
        name=primary_key
    )

    m = folium.Map(location=[-23, -46],
                zoom_start=3, no_wrap=True,world_copy_jump=True, tiles=tile_layer, 
                )

    locate_control = LocateControl()
    locate_control.add_to(m)

    mouse_position = MousePosition()
    mouse_position.add_to(m)

    with open('datasets/world-countries.json') as handle:
        country_geo = json.loads(handle.read())

    country_layer = folium.FeatureGroup(name='Countries')
    country_layer.add_to(m)

    try:
        # Load the CSV file into a DataFrame
        iso_code_dict = {}
        for _, row in df.iterrows():
            iso_code = None
            if 'iso_code' in row:
                iso_code = row['iso_code']
            elif 'Code' in row:
                iso_code = row['Code']
            else:
                try:
                    iso_code = pycountry.countries.get(name=row['Country'])
                    if iso_code is not None:
                        iso_code = iso_code.alpha_3
                    else:
                        continue
                except LookupError:
                    continue

            if iso_code not in iso_code_dict:
                iso_code_dict[iso_code] = row
    except:
        print('Error loading CSV file')

    print('Time taken:', int(time.time() * 1000) - current_time_ms, 'ms')

    def thread(feature):
        iso_code = feature['id']
        
        failure = False
        if iso_code in iso_code_dict:
            data = iso_code_dict[iso_code]
            if not primary_key in data or pd.isna(data[primary_key]):
                failure = True
        else:
            failure = True

        if failure:
            folium.GeoJson(
                feature,
                style_function=lambda feature: {
                    'fillColor': 'white',
                    'color': 'black',
                    'weight': 2,
                    'fillOpacity': 1,
                },
                tooltip=f'No data available for this country in {year}.'
            ).add_to(country_layer)
            return
        
        value = ((data[primary_key] - min_value) / (max_value - min_value)) if primary_key in data else 0.25
        value_dict[iso_code] = [
            0.2 + value * 0.8,
            gradient
        ]

        primary_key_pretty = str(primary_key.replace('_', ' ').title())

        folium.GeoJson(
            feature,
            style_function=lambda feature: {
                'fillColor': value_dict[feature['id']][1](value_dict[feature['id']][0]),
                'color': 'black',
                'weight': 2,
                'fillOpacity': 0.7,
            },
            zoom_on_click = True,
            tooltip=f'<h4>{data["Country"]} {year} {countryflag.getflag([data["Country"]])}</h4><h6>{primary_key_pretty}: {data[primary_key]}</h6>'
        ).add_to(country_layer)

    for feature in country_geo['features']:
        try:
            thread(feature)
        except:
            print('Error with', feature['id'])

    print('Time taken:', int(time.time() * 1000) - current_time_ms, 'ms')

    try:
        search_control = Search(
            layer=country_layer,
            geom_type='Polygon',
            placeholder='Search for a country',
            collapsed=False,
            search_label='name',
            search_zoom=6,
            position='topright'
        )
        search_control.add_to(m)

        gradient.add_to(m)
    except:
        print('Search failed')

    conoconColor = {
        'Climate Change' : 'red',
        'Water' : 'blue',
        'Biodiversity' : 'lightgreen',
        'Stakeholder Engagement' : 'orange'
    }

    try:
        descriptions = []
        with open('IconDescriptions.txt', 'r', encoding='utf-8') as file:
            fulltext = ''.join(file.readlines())

            descriptions = re.split(';\n[0-9]+:', fulltext)
            descriptions = [x.strip() for x in descriptions]
            descriptions = [x for x in descriptions if x]

        print('Time taken:', int(time.time() * 1000) - current_time_ms, 'ms')
    except:
        print('IconDescriptions.txt is empty')

    # Parse IconLocationsPercent.txt
    icon_data = []

    try:
        with open('IconLocationsPercent.txt', 'r') as file:
            for line in file:
                line = line.strip()
                if line: #new item "country name" added to list, be sure to account for this
                    name, variant, lat, lon, country_name = line.split(', ')
                    lat = -(float(lat) * 180 / 100 - 90) + 20 #why is there an outer negative sign?
                    lon = float(lon) * 360 / 100 - 180 + 18
                    color = conoconColor.get(variant, 'red')
                    desc = f'<h3>{country_name} {countryflag.getflag([country_name])}</h3><h5>{name}</h5>{descriptions.pop()}'
                    popup = folium.Popup(desc, max_width=300, lazy = True)
                    icon_data.append([lat, lon, popup, color])
    except:
        print('IconLocationsPercent.txt is empty')

    # Create IconMarkers and add them to the map
    try:
        for data in icon_data:
            folium.Marker(
                location=(data[0], data[1]),
                icon=folium.Icon(color=data[3]),
                popup=data[2],

            ).add_to(m)
    except:
        print('IconLocationsPercent.txt is empty')

    fullscreen_control = Fullscreen()
    fullscreen_control.add_to(m)

    return m

@lru_cache(maxsize=2)
def create_map(filename, year, primary_key):
    current_time_ms = int(time.time() * 1000)
    schema = parse_schemas.get_schema()
    gradient = schema[filename][2]
    df = pd.read_csv(f'Backend/CSV/{filename}.csv')
    try:
        m = create_map_2(df, year, primary_key, gradient)
    except:
        m = folium.Map(location=[-23, -46], zoom_start=3, no_wrap=True, world_copy_jump=True)
    print('Time taken:', int(time.time() * 1000) - current_time_ms, 'ms')
    return m

if __name__ == '__main__':
    m = create_map('agricultural-land', 2020, 'Agricultural land')
    #m = create_map('fossil-fuels-per-capita', 2019, 'Fossil fuels per capita (kWh)')
    #m = create_map('fossil-fuel-primary-energy', 2019, 'Fossil fuels (TWh)')
    m.save('index.html')
    webbrowser.open('index.html')