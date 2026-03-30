# PyInstaller hook for pandas
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = collect_all('pandas')

# Add additional pandas submodules
hiddenimports += [
    'pandas._libs._cyutility',
    'pandas._libs.tslibs.base',
    'pandas._libs.tslibs.np_datetime',
    'pandas._libs.tslibs.nattype',
    'pandas._libs.tslibs.timezones',
    'pandas._libs.tslibs.conversion',
    'pandas._libs.tslibs.timestamps',
    'pandas._libs.tslibs.period',
    'pandas._libs.tslibs.tzconversion',
    'pandas._libs.tslibs.offsets',
    'pandas._libs.tslibs.strptime',
    'pandas._libs.tslibs.parsing',
    'pandas._libs.tslibs.fields',
    'pandas._libs.tslibs.ccalendar',
    'pandas._libs.tslibs.dtypes',
    'pandas._libs.interval',
    'pandas._libs.hashtable',
    'pandas._libs.missing',
    'pandas._libs.lib',
    'pandas._libs.hashing',
    'pandas._libs.index',
    'pandas._libs.indexing',
    'pandas._libs.internals',
    'pandas._libs.join',
    'pandas._libs.reshape',
    'pandas._libs.sparse',
    'pandas._libs.testing',
    'pandas._libs.writers',
    'pandas._libs.reduction',
    'pandas._libs.ops',
    'pandas._libs.ops_dispatch',
    'pandas._libs.properties',
    'pandas._libs.json',
    'pandas._libs.parsers',
]
