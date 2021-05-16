import toml
from datetime import datetime
from datetime import timedelta
import pandas as pd
from tqdm import tqdm
import json
from logger import log

deps = pd.read_csv('utils/departement2021.csv', dtype=str)
deps = deps[['DEP', 'REG']]
deps = deps.rename(columns={'DEP': 'dep', 'REG': 'reg'})
deps = deps.drop_duplicates(keep="first")

countries = ["National"]


def get_color(val, trendType):
    """Determine if evolution is positive or negative.

    From trend type - determined in config.toml for each KPIs,
    picking right color to return
    """
    if(val > 0):
        if(trendType == 'normal'):
            color = 'red'
        else:
            color = 'green'
    else:
        if(trendType == 'normal'):
            color = 'green'
        else:
            color = 'red'
    return color


def get_empty_kpi():
    """Initialize result Dictionnary."""
    indicateurResult = {}
    indicateurResult['nom'] = []
    indicateurResult['unite'] = []
    indicateurResult['france'] = []
    indicateurResult['regions'] = []
    indicateurResult['departements'] = []
    return indicateurResult


def get_config(group):
    """Retrieve config from config.toml file."""
    config = toml.load('./config.toml')
    return config[group]


def format_dict(
    last_value, last_date, evol, evol_percentage, level,
    code_level, dfvalues, column, trendType
):
    """Format result for each KPI and each geo level.

    Dictionnary is filled with values pre-calculated and
    passed to this function.
    This function is called for each kpi and each geozones
    """
    resdict = {}
    resdict['last_value'] = str(last_value)
    resdict['last_date'] = str(last_date)
    resdict['evol'] = str(evol)
    resdict['evol_percentage'] = str(round(evol_percentage, 2))
    resdict['evol_color'] = get_color(evol_percentage, trendType)
    resdict['level'] = level
    resdict['code_level'] = str(code_level)
    resdict['values'] = []
    for index, row in dfvalues.iterrows():
        interdict = {}
        interdict['value'] = str(round(row[column], 2))
        interdict['date'] = row['date']
        resdict['values'].append(interdict)
    return resdict


def get_rolling_average(date, df, column):
    """Calculate rolling average from a column.

    We apply mean for each values of a specific column
    within the range of last week date and date itself
    """
    lowestDate = datetime.strftime(
        datetime.strptime(date, "%Y-%m-%d") - timedelta(days=6), "%Y-%m-%d"
    )
    return df[
        (df['date'] >= lowestDate)
        &
        (df['date'] <= date)
    ].mean()[column].mean().round(0)


def process_stock(df, level, code_level, trendType, column, shorten=False):
    """Calculate values for Stock type KPIs.

    Common function which calculate the evolution of a column
    within a week and its percentage.
    """
    df = df.sort_values(by=['date'])
    df = df.reset_index(drop=True)
    if(shorten):
        df = df[:-3]

    df['date_7days_ago'] = df['date'].apply(lambda x: datetime.strftime(
        datetime.strptime(x, "%Y-%m-%d") - timedelta(days=7), "%Y-%m-%d"
    ))
    df['7days_ago'] = df['date_7days_ago'].apply(lambda x: df[df['date'] == x][column].iloc[0] if(df[df['date'] == x].shape[0] > 0) else None)
    df['evol'] = df[column] - df['7days_ago']
    df['evol_percentage'] = df['evol'] / df['7days_ago'] * 100

    return format_dict(
        round(df[df['date'] == df.date.max()][column].iloc[0], 2),
        df.date.max(),
        round(df[df['date'] == df.date.max()]['evol'].iloc[0], 2),
        df[df['date'] == df.date.max()]['evol_percentage'].iloc[0],
        level,
        code_level,
        df[[column, 'date']],
        column,
        trendType
    )


def process_rolling_average(df, level, code_level, trendType, column):
    """Calculate values for Mean type KPIs.

    Common function which calculate the mean of a column and
    its evolution within a week and its percentage.
    """
    df = df.sort_values(by=['date'])
    df = df.reset_index(drop=True)

    df['date_7days_ago'] = df['date'].apply(lambda x: datetime.strftime(
        datetime.strptime(x, "%Y-%m-%d") - timedelta(days=7), "%Y-%m-%d"
    ))
    df['mean'] = df['date'].apply(lambda x: get_rolling_average(x, df, column))
    df['mean_7days_ago'] = df['date_7days_ago'].apply(lambda x: df[df['date'] == x]['mean'].iloc[0] if(df[df['date'] == x].shape[0] > 0) else None)
    df['evol_mean'] = df['mean'] - df['mean_7days_ago']
    df['evol_mean_percentage'] = df['evol_mean'] / df['mean_7days_ago'] * 100

    return format_dict(
        int(df[df['date'] == df.date.max()]['mean'].iloc[0]),
        df.date.max(),
        int(df[df['date'] == df.date.max()]['evol_mean'].iloc[0]),
        df[df['date'] == df.date.max()]['evol_mean_percentage'].iloc[0],
        level,
        code_level,
        df[['mean', 'date']],
        'mean',
        trendType
    )


def save_result(res, name):
    """Save KPI in a dedicated file.

    Files are saved in dist directory.
    """
    with open('dist/'+name+'.json','w') as fp:
        json.dump(res, fp)


def enrich_dataframe(df, name):
    """Enrich dataframe for KPIs that need to be calculated.

    Only three KPIs are needed to be calculated :
    taux_incidence, taux_positivite and taux_occupation
    """
    if(name == 'taux_incidence'):
        df['taux_incidence'] = df['P']*100000/df['pop']
    if(name == 'taux_positivite'):
        df['taux_positivite'] = df['P']/df['T'] * 100
    if(name == 'taux_occupation'):
        df['TO'] = df['TO']*100
    if(name == 'couverture_vaccinale_dose1'):
        df['couverture_vaccinale_dose1'] = df['couv_dose1']
        df['date'] = df['jour']
    if(name == 'couverture_vaccinale_complet'):
        df['couverture_vaccinale_complet'] = df['couv_complet']
        df['date'] = df['jour']

    return df


def get_taux(name, formatDate):
    """Process each geozones for Rate type of KPIs.

    Common function which orchestrate processing for Rate type of KPIs
    (there is some exception, see get_taux_specific)
    """
    indicateurResult = get_empty_kpi()
    config = get_config(name)
    log.debug('Processing - '+name)

    indicateurResult['nom'] = config['nom']
    indicateurResult['unite'] = config['unite']

    df = pd.read_csv(
        'files_new/'+config['res_id_fra'],
        sep=None,
        engine='python',
        dtype={'reg': str, 'dep': str}
    )
    df = enrich_dataframe(df, name)
    if(formatDate):
        df['date'] = df['semaine_glissante'].apply(lambda x: str(x)[11:])
    for country in tqdm(countries, desc="Processing National"):
        res = process_stock(
            df,
            'nat',
            'fra',
            config['trendType'],
            name
        )
        indicateurResult['france'].append(res)

    df = pd.read_csv(
        'files_new/'+config['res_id_reg'],
        sep=None,
        engine='python',
        dtype={'reg': str, 'dep': str}
    )
    df = enrich_dataframe(df, name)
    if(formatDate):
        df['date'] = df['semaine_glissante'].apply(lambda x: str(x)[11:])
    for reg in tqdm(df.reg.unique(), desc="Processing Régions"):
        res = process_stock(
            df[df['reg'] == reg].copy(),
            'reg',
            reg,
            config['trendType'],
            name
        )
        indicateurResult['regions'].append(res)

    df = pd.read_csv(
        'files_new/'+config['res_id_dep'],
        sep=None,
        engine='python',
        dtype={'reg': str, 'dep': str}
    )
    df = enrich_dataframe(df, name)
    if(formatDate):
        df['date'] = df['semaine_glissante'].apply(lambda x: str(x)[11:])
    for dep in tqdm(df.dep.unique(), desc="Processing Départements"):
        res = process_stock(
            df[df['dep'] == dep].copy(),
            'dep',
            dep,
            config['trendType'],
            name
        )
        indicateurResult['departements'].append(res)

    save_result(indicateurResult, name)


def get_kpi_by_type(df, level, code_level, trendType, column, mean):
    """Redirect to good function depending of type of KPI needed.

    If mean param is set to True, we need to calculate the mean of kpis,
    if not, we calculate the stock.
    """
    if(mean):
        res = process_rolling_average(df, level, code_level, trendType, column)
    else:
        res = process_stock(df, level, code_level, trendType, column)
    return res


def get_kpi(name, column, mean, transformDF=False):
    """Process each geozones for Number type of KPIs.

    Common function which orchestrate processing for Number type of KPIs
    (there is some exception, see get_kpi_only_france)
    """
    indicateurResult = get_empty_kpi()
    config = get_config(name)
    log.debug('Processing - '+name)

    indicateurResult['nom'] = config['nom']
    indicateurResult['unite'] = config['unite']

    df = pd.read_csv(
        'files_new/'+config['res_id'],
        sep=None,
        engine='python',
        dtype={'reg': str, 'dep': str}
    )

    # Specificity KPI vaccins
    if(transformDF):
        df = df.rename(columns={'jour': 'date'})
        df = pd.merge(df, deps, on='dep', how='left')
        df = df[df['reg'].notna()]

    # Specifity cas_positifs
    if(column == 'pos_7j'):
        df = df[df['pos_7j'].notna()]
        df['pos7j_moyen'] = df['pos_7j'] / 7
        df['pos7j_moyen'] = df['pos7j_moyen'].astype(int)
        column = 'pos7j_moyen'

    df = df[['dep', 'reg', 'date', column]]
    for country in tqdm(countries, desc="Processing National"):
        res = get_kpi_by_type(
            df.groupby(['date'], as_index=False).sum(),
            'nat',
            'fra',
            config['trendType'],
            column,
            mean
        )
        indicateurResult['france'].append(res)

    dfinter = df.groupby(['date', 'reg'], as_index=False).sum()
    for reg in tqdm(df.reg.unique(), desc="Processing Régions"): 
        res = get_kpi_by_type(
            dfinter[dfinter['reg'] == reg].copy(),
            'reg',
            reg,
            config['trendType'],
            column,
            mean
        )
        indicateurResult['regions'].append(res)

    for dep in tqdm(df.dep.unique(), desc="Processing Départements"):
        res = get_kpi_by_type(
            df[df['dep'] == dep].copy(),
            'dep',
            dep,
            config['trendType'],
            column,
            mean
        )
        indicateurResult['departements'].append(res)

    save_result(indicateurResult, name)


def get_kpi_only_france(name, column, mean, transformDF=False):
    """Process only National level for Number type of KPIs.

    Specific function dedicated to deces_total KPI, which has no
    regions or departments data in original source.
    """
    indicateurResult = get_empty_kpi()
    config = get_config(name)
    log.debug('Processing - '+name)

    indicateurResult['nom'] = config['nom']
    indicateurResult['unite'] = config['unite']

    df = pd.read_csv(
        'files_new/'+config['res_id'],
        sep=None,
        engine='python',
        dtype={'reg': str, 'dep': str}
    )

    df = df[['date', column]]
    for country in tqdm(countries, desc="Processing National"):
        res = get_kpi_by_type(
            df.groupby(['date'], as_index=False).sum(),
            'nat',
            'fra',
            config['trendType'],
            column,
            mean
        )
        indicateurResult['france'].append(res)

    save_result(indicateurResult, name)


def get_taux_specific(name, column):
    """Process each geozone for Rate type of KPIs with exception.

    Specific function dedicated to taux_occupation and facteur_reproduction
    These KPIs has no region data in original source but values in
    departments data could be retrieve for region.
    So specific manipulation for these KPIs
    """
    indicateurResult = get_empty_kpi()
    config = get_config(name)
    log.debug('Processing - '+name)

    indicateurResult['nom'] = config['nom']
    indicateurResult['unite'] = config['unite']

    df = pd.read_csv(
        'files_new/'+config['res_id_fra'],
        sep=None,
        engine='python',
        dtype={'reg': str, 'dep': str}
    )
    df = df[df[column].notna()]
    df = df.sort_values(by=['date'])
    df = enrich_dataframe(df, name)

    for country in tqdm(countries, desc="Processing National"):
        res = process_stock(
            df,
            'nat',
            'fra',
            config['trendType'],
            column
        )
        indicateurResult['france'].append(res)

    df = pd.read_csv(
        'files_new/'+config['res_id_reg'],
        sep=None,
        engine='python',
        dtype={'reg': str, 'dep': str}
    )
    df = df[df[column].notna()]
    df = df.sort_values(by=['date'])
    df = enrich_dataframe(df, name)

    for reg in tqdm(df.reg.unique(), desc="Processing Régions"):
        res = process_stock(
            df[df['dep'] == df[df['reg'] == reg].dep.unique()[0]].copy(),
            'reg',
            reg,
            config['trendType'],
            column
        )
        indicateurResult['regions'].append(res)

    df = pd.read_csv(
        'files_new/'+config['res_id_dep'],
        sep=None,
        engine='python',
        dtype={'reg': str, 'dep': str}
    )
    df = df[df[column].notna()]
    df = df.sort_values(by=['date'])
    df = enrich_dataframe(df, name)

    for dep in tqdm(df.dep.unique(), desc="Processing Départements"):
        res = process_stock(
            df[df['dep'] == dep].copy(),
            'dep',
            dep,
            config['trendType'],
            column
        )
        indicateurResult['departements'].append(res)

    save_result(indicateurResult, name)
