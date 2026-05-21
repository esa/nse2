# Contact Plan
# Defines scheduled contacts and fixed links between nodes.
#
# Directives:
#   s loop <n>        : loop behaviour — 1 to repeat indefinitely, 0 (or omit) for no loop
#   a <contact|fixed> : add a fixed link or a fluctuating contact with properties described below 
#
# Columns:
#   type      : 'a contact' for scheduled links, 'a fixed' for fixed links
#   start     : contact start time relative to scenario start (seconds, +offset)
#   end       : contact end time relative to scenario start (seconds, +offset)
#   src       : source node (node ID | node name)
#   dst       : destination node (node ID | node name | `dev:<interfacename>`)
#   bw        : bandwidth (e.g. 30mbit)
#   loss      : packet loss percentage (e.g. 0.0)
#   delay     : one-way propagation delay (ms)
#   jitter    : delay jitter (ms)
#   symmetric : '=' to apply the link in both directions, omit for one-way


# <type> <src> <dst>  [bw]   [loss] [delay] [jitter] [=]
a fixed  rcc1  gs1   100mbit  0.0    150.0    0.0
a fixed  gs1   rcc1  100mbit  0.0    150.0    0.0

a fixed  rcc1  rcc2  100mbit  0.0     75.0    0.0
a fixed  rcc2  rcc1  100mbit  0.0     75.0    0.0

a fixed  rcc1  gs2   100mbit  0.0    150.0    0.0
a fixed  gs2   rcc1  100mbit  0.0    150.0    0.0

a fixed  rcc1  b1cc  100mbit  0.0     75.0    0.0
a fixed  b1cc  rcc1  100mbit  0.0     75.0    0.0

a fixed  rcc1  r1cc  100mbit  0.0     75.0    0.0
a fixed  r1cc  rcc1  100mbit  0.0     75.0    0.0

a fixed  rcc1  u1cc  100mbit  0.0     75.0    0.0
a fixed  u1cc  rcc1  100mbit  0.0     75.0    0.0

a fixed  gs1   rcc2  100mbit  0.0    150.0    0.0
a fixed  rcc2  gs1   100mbit  0.0    150.0    0.0

a fixed  rcc2  gs2   100mbit  0.0    150.0    0.0
a fixed  gs2   rcc2  100mbit  0.0    150.0    0.0

a fixed  rcc2  b1cc  100mbit  0.0     75.0    0.0
a fixed  b1cc  rcc2  100mbit  0.0     75.0    0.0

a fixed  rcc2  r1cc  100mbit  0.0     75.0    0.0
a fixed  r1cc  rcc2  100mbit  0.0     75.0    0.0

a fixed  rcc2  u1cc  100mbit  0.0    150.0    0.0
a fixed  u1cc  rcc2  100mbit  0.0    150.0    0.0

a fixed  lgw   user1  54mbit  0.0      3.0    0.0
a fixed  user1 lgw    54mbit  0.0      3.0    0.0


# <type>   <start>   <end>  <src>  <dst>   [bw]  [loss] [delay] [jitter] [=]
a contact       +0   +36393 gs1    base1  30mbit  0.0    1339    0        =
a contact       +0   +33669 gs1    lgw    30mbit  0.0    1408    0        =
a contact       +0   +36009 gs1    relay1 30mbit  0.0    1344    0        =
a contact       +0  +305876 base1  lgw    15mbit  0.0     233    0        =
a contact       +0   +50167 base1  relay2 15mbit  0.0      46    0        =
a contact       +0  +168640 rover1 lgw    15mbit  0.0     237    0        =
a contact       +0  +315010 lgw    relay1 30mbit  0.0     246    0        =
a contact       +0   +57426 lgw    relay2 30mbit  0.0     203    0        =
a contact    +1398    +5962 rover1 relay1 15mbit  0.0       8    0        =
a contact    +6984   +78483 base1  relay1 15mbit  0.0      22    0        =
a contact   +33183   +56595 rover1 relay2 15mbit  0.0      46    0        =
a contact   +54654   +92627 gs2    lgw    30mbit  0.0    1413    0        =
a contact   +57055   +92665 gs2    base1  30mbit  0.0    1346    0        =
a contact   +57225   +92479 gs2    relay2 30mbit  0.0    1351    0        =
a contact   +59191  +143777 lgw    relay2 30mbit  0.0     246    0        =
a contact   +65388  +136543 base1  relay2 15mbit  0.0      23    0        =
a contact   +84012  +123637 gs1    relay1 30mbit  0.0    1341    0        =
a contact   +84189  +124031 gs1    base1  30mbit  0.0    1346    0        =
a contact   +84588  +121324 gs1    lgw    30mbit  0.0    1411    0        =
a contact   +87460   +97749 rover1 relay1 15mbit  0.0       8    0        =
a contact   +93378  +164891 base1  relay1 15mbit  0.0      22    0        =
a contact  +125597  +143102 rover1 relay2 15mbit  0.0      40    0        =
a contact  +142650  +181847 gs2    lgw    30mbit  0.0    1399    0        =
a contact  +144911  +182319 gs2    base1  30mbit  0.0    1344    0        =
a contact  +145092  +182143 gs2    relay2 30mbit  0.0    1342    0        =
a contact  +145783  +230220 lgw    relay2 30mbit  0.0     220    0        =
a contact  +151769  +222919 base1  relay2 15mbit  0.0      23    0        =
a contact  +173810  +189519 rover1 relay1 15mbit  0.0       8    0        =
a contact  +174072  +209382 gs1    lgw    30mbit  0.0    1390    0        =
a contact  +174145  +211561 gs1    base1  30mbit  0.0    1343    0        =
a contact  +175264  +211150 gs1    relay1 30mbit  0.0    1353    0        =
a contact  +179778  +251303 base1  relay1 15mbit  0.0      22    0        =
a contact  +217894  +229532 rover1 relay2 15mbit  0.0      32    0        =
a contact  +231108  +271326 gs2    lgw    30mbit  0.0    1368    0        =
a contact  +232506  +489649 lgw    relay2 30mbit  0.0     156    0        =
a contact  +232780  +271949 gs2    base1  30mbit  0.0    1338    0        =
a contact  +232952  +271790 gs2    relay2 30mbit  0.0    1330    0        =
a contact  +238147  +309295 base1  relay2 15mbit  0.0      23    0        =
a contact  +260265  +281112 rover1 relay1 15mbit  0.0       8    0        =
a contact  +263734  +298470 gs1    lgw    30mbit  0.0    1353    0        =
a contact  +264189  +284145 gs1    base1  30mbit  0.0    1335    0        =
a contact  +264280  +298609 gs1    relay1 30mbit  0.0    1352    0        =
a contact  +266182  +337720 base1  relay1 15mbit  0.0      22    0        =
a contact  +309774  +315807 rover1 relay2 15mbit  0.0      22    0        =
a contact  +316936  +343931 lgw    relay1 30mbit  0.0      60    0        =
a contact  +320738  +342922 gs2    base1  30mbit  0.0    1327    0        =
a contact  +320895  +361500 gs2    relay2 30mbit  0.0    1317    0        =
a contact  +320945  +362315 gs2    lgw    30mbit  0.0    1328    0        =
a contact  +324444  +873204 base1  lgw    15mbit  0.0      26    0        =
a contact  +324523  +395673 base1  relay2 15mbit  0.0      23    0        =
a contact  +346343  +430597 lgw    relay1 30mbit  0.0      82    0        =
a contact  +346793  +372514 rover1 relay1 15mbit  0.0       8    0        =
a contact  +352591  +424140 base1  relay1 15mbit  0.0      22    0        =
a contact  +354586  +386079 gs1    relay1 30mbit  0.0    1343    0        =
a contact  +355472  +385140 gs1    lgw    30mbit  0.0    1336    0        =
a contact  +407834  +452189 gs2    lgw    30mbit  0.0    1346    0        =
a contact  +409010  +451346 gs2    relay2 30mbit  0.0    1301    0        =
a contact  +410899  +482054 base1  relay2 15mbit  0.0      23    0        =
a contact  +432679  +517141 lgw    relay1 30mbit  0.0     182    0        =
a contact  +433395  +463849 rover1 relay1 15mbit  0.0       8    0        =
a contact  +439003  +510562 base1  relay1 15mbit  0.0      22    0        =
a contact  +445148  +473644 gs1    relay1 30mbit  0.0    1330    0        =
a contact  +446900  +471111 gs1    lgw    30mbit  0.0    1350    0        =
a contact  +489915  +575988 lgw    relay2 30mbit  0.0     218    0        =
a contact  +495432  +542097 gs2    lgw    30mbit  0.0    1351    0        =
a contact  +497276  +568440 base1  relay2 15mbit  0.0      22    0        =
a contact  +497393  +541388 gs2    relay2 30mbit  0.0    1284    0        =
a contact  +518939  +603617 lgw    relay1 30mbit  0.0     231    0        =
a contact  +520101  +555355 rover1 relay1 15mbit  0.0       9    0        =
a contact  +525419  +596985 base1  relay1 15mbit  0.0      22    0        =
a contact  +536046  +561427 gs1    relay1 30mbit  0.0    1313    0        =
a contact  +538581  +557476 gs1    lgw    30mbit  0.0    1348    0        =
a contact  +576705  +662567 lgw    relay2 30mbit  0.0     244    0        =
a contact  +583656  +654830 base1  relay2 15mbit  0.0      22    0        =
a contact  +583702  +632183 gs2    lgw    30mbit  0.0    1341    0        =
a contact  +586151  +631640 gs2    relay2 30mbit  0.0    1267    0        =
a contact  +605155  +690025 lgw    relay1 30mbit  0.0     245    0        =
a contact  +606975  +647420 rover1 relay1 15mbit  0.0      10    0        =
a contact  +611838  +683408 base1  relay1 15mbit  0.0      22    0        =
a contact  +627243  +649630 gs1    relay1 30mbit  0.0    1294    0        =
a contact  +630605  +644514 gs1    lgw    30mbit  0.0    1329    0        =
a contact  +663241  +881110 lgw    relay2 30mbit  0.0     237    0        =
a contact  +670038  +741226 base1  relay2 15mbit  0.0      22    0        =
a contact  +672795  +722339 gs2    lgw    30mbit  0.0    1315    0        =
a contact  +675389  +722031 gs2    relay2 30mbit  0.0    1250    0        =
a contact  +691314  +776295 lgw    relay1 30mbit  0.0     227    0        =
a contact  +694170  +740719 rover1 relay1 15mbit  0.0      12    0        =
a contact  +698258  +769829 base1  relay1 15mbit  0.0      22    0        =
a contact  +718464  +738583 gs1    relay1 30mbit  0.0    1275    0        =
a contact  +721854  +733476 gs1    lgw    30mbit  0.0    1295    0        =
a contact  +750670  +752526 rover1 relay2 15mbit  0.0       9    0        =
a contact  +756424  +827627 base1  relay2 15mbit  0.0      22    0        =
a contact  +762896  +812247 gs2    lgw    30mbit  0.0    1276    0        =
a contact  +765169  +812385 gs2    relay2 30mbit  0.0    1235    0        =
a contact  +777374  +861401 lgw    relay1 30mbit  0.0     174    0        =
a contact  +782086  +836275 rover1 relay1 15mbit  0.0      16    0        =
a contact  +784678  +856247 base1  relay1 15mbit  0.0      22    0        =
a contact  +809154  +828655 gs1    relay1 30mbit  0.0    1258    0        =
a contact  +810451  +826124 gs1    lgw    30mbit  0.0    1251    0        =
a contact  +836496  +843964 rover1 relay2 15mbit  0.0       8    0        =
a contact  +842815  +914034 base1  relay2 15mbit  0.0      22    0        =
a contact  +854234  +902999 gs2    lgw    30mbit  0.0    1229    0        =
a contact  +855450  +902471 gs2    relay2 30mbit  0.0    1224    0        =
a contact  +862917  +883045 lgw    relay1 30mbit  0.0      65    0        =
a contact  +871098  +942662 base1  relay1 15mbit  0.0      22    0        =
a contact  +871806  +933736 rover1 relay1 15mbit  0.0      23    0        =
a contact  +883413  +919880 lgw    relay2 30mbit  0.0      64    0        =
a contact  +884232  +950068 lgw    relay1 30mbit  0.0      54    0        =
a contact  +891841 +1423798 base1  lgw    15mbit  0.0      30    0        =
a contact  +898859  +919863 gs1    relay1 30mbit  0.0    1245    0        =
a contact  +898868  +919902 gs1    lgw    30mbit  0.0    1219    0        =
a contact  +922343 +1006842 lgw    relay2 30mbit  0.0      98    0        =
a contact  +922836  +935810 rover1 relay2 15mbit  0.0       8    0        =
a contact  +929211 +1000447 base1  relay2 15mbit  0.0      22    0        =
a contact  +946062  +992119 gs2    relay2 30mbit  0.0    1217    0        =
a contact  +946159  +994018 gs2    lgw    30mbit  0.0    1231    0        =
a contact  +952075 +1036243 lgw    relay1 30mbit  0.0     140    0        =
a contact  +957516 +1029072 base1  relay1 15mbit  0.0      22    0        =
a contact  +965217 +1028193 rover1 relay1 15mbit  0.0      36    0        =
a contact  +987629 +1011662 gs1    relay1 30mbit  0.0    1236    0        =
a contact  +990639 +1010198 gs1    lgw    30mbit  0.0    1243    0        =
a contact +1008939 +1093458 lgw    relay2 30mbit  0.0     191    0        =
a contact +1009293 +1027974 rover1 relay2 15mbit  0.0       8    0        =
a contact +1015613 +1086863 base1  relay2 15mbit  0.0      22    0        =
a contact +1036637 +1083591 gs2    lgw    30mbit  0.0    1254    0        =
a contact +1036772 +1081287 gs2    relay2 30mbit  0.0    1216    0        =
a contact +1037995 +1122465 lgw    relay1 30mbit  0.0     211    0        =
a contact +1043932 +1115477 base1  relay1 15mbit  0.0      22    0        =
a contact +1061147 +1118243 rover1 relay1 15mbit  0.0      46    0        =
a contact +1075799 +1103443 gs1    relay1 30mbit  0.0    1232    0        =
a contact +1079414 +1101690 gs1    lgw    30mbit  0.0    1261    0        =
a contact +1095336 +1179990 lgw    relay2 30mbit  0.0     234    0        =
a contact +1095819 +1120240 rover1 relay2 15mbit  0.0       8    0        =
a contact +1102020 +1173284 base1  relay2 15mbit  0.0      22    0        =
a contact +1124205 +1208679 lgw    relay1 30mbit  0.0     241    0        =
a contact +1127040 +1172249 gs2    lgw    30mbit  0.0    1267    0        =
a contact +1127407 +1170035 gs2    relay2 30mbit  0.0    1219    0        =
a contact +1130344 +1201876 base1  relay1 15mbit  0.0      22    0        =
a contact +1155825 +1206263 rover1 relay1 15mbit  0.0      52    0        =
a contact +1163653 +1194909 gs1    relay1 30mbit  0.0    1231    0        =
a contact +1166902 +1193249 gs1    lgw    30mbit  0.0    1270    0        =
a contact +1181632 +1266485 lgw    relay2 30mbit  0.0     241    0        =
a contact +1182412 +1212577 rover1 relay2 15mbit  0.0       8    0        =
a contact +1188432 +1259706 base1  relay2 15mbit  0.0      22    0        =
a contact +1210533 +1294882 lgw    relay1 30mbit  0.0     237    0        =
a contact +1216751 +1288270 base1  relay1 15mbit  0.0      22    0        =
a contact +1217249 +1260232 gs2    lgw    30mbit  0.0    1270    0        =
a contact +1217899 +1258468 gs2    relay2 30mbit  0.0    1226    0        =
a contact +1248805 +1293500 rover1 relay1 15mbit  0.0      54    0        =
a contact +1251373 +1286031 gs1    relay1 30mbit  0.0    1234    0        =
a contact +1253791 +1284522 gs1    lgw    30mbit  0.0    1268    0        =
a contact +1267800 +1353106 lgw    relay2 30mbit  0.0     214    0        =
a contact +1269089 +1305113 rover1 relay2 15mbit  0.0       9    0        =
a contact +1274848 +1346130 base1  relay2 15mbit  0.0      22    0        =
a contact +1296931 +1381033 lgw    relay1 30mbit  0.0     197    0        =
a contact +1303154 +1374659 base1  relay1 15mbit  0.0      22    0        =
a contact +1307348 +1347657 gs2    lgw    30mbit  0.0    1261    0        =
a contact +1308270 +1346697 gs2    relay2 30mbit  0.0    1238    0        =
a contact +1339080 +1376897 gs1    relay1 30mbit  0.0    1240    0        =
a contact +1340307 +1375703 gs1    lgw    30mbit  0.0    1256    0        =
a contact +1340837 +1380395 rover1 relay1 15mbit  0.0      54    0        =
a contact +1353557 +1428101 lgw    relay2 30mbit  0.0     148    0        =
a contact +1355894 +1398102 rover1 relay2 15mbit  0.0      10    0        =
a contact +1361268 +1432554 base1  relay2 15mbit  0.0      22    0        =
a contact +1383352 +1431208 lgw    relay1 30mbit  0.0     112    0        =
a contact +1389552 +1461043 base1  relay1 15mbit  0.0      22    0        =
a contact +1397698 +1434698 gs2    lgw    30mbit  0.0    1244    0        =
a contact +1398581 +1434825 gs2    relay2 30mbit  0.0    1251    0        =
a contact +1413730 +1434726 gs2    base1  30mbit  0.0    1223    0        =
a contact +1426264 +1468037 gs1    lgw    30mbit  0.0    1238    0        =
a contact +1426861 +1462447 gs1    relay1 30mbit  0.0    1247    0        =
a contact +1430930 +1440639 lgw    relay2 30mbit  0.0      37    0        =
a contact +1432487 +1467112 rover1 relay1 15mbit  0.0      53    0        =
a contact +1433766 +1728149 lgw    relay1 30mbit  0.0      67    0        =
a contact +1442350 +1991524 base1  lgw    15mbit  0.0      35    0        =
a contact +1442920 +1491912 rover1 relay2 15mbit  0.0      11    0        =
a contact +1443023 +1526040 lgw    relay2 30mbit  0.0      50    0        =
a contact +1447690 +1518977 base1  relay2 15mbit  0.0      23    0        =
a contact +1457592 +1467485 gs1    base1  30mbit  0.0    1232    0        =
a contact +1475944 +1547424 base1  relay1 15mbit  0.0      22    0        =
a contact +1488795 +1522925 gs2    base1  30mbit  0.0    1247    0        =
a contact +1488896 +1522949 gs2    relay2 30mbit  0.0    1266    0        =
a contact +1489371 +1524949 gs2    lgw    30mbit  0.0    1265    0        =
a contact +1514433 +1558072 gs1    base1  30mbit  0.0    1251    0        =
a contact +1514797 +1549555 gs1    relay1 30mbit  0.0    1255    0        =
a contact +1516463 +1558131 gs1    lgw    30mbit  0.0    1279    0        =
a contact +1524117 +1553723 rover1 relay1 15mbit  0.0      51    0        =
a contact +1528312 +1612295 lgw    relay2 30mbit  0.0     169    0        =
a contact +1530379 +1586838 rover1 relay2 15mbit  0.0      14    0        =
a contact +1534113 +1605396 base1  relay2 15mbit  0.0      23    0        =
a contact +1553012 +1558165 gs1    relay1 30mbit  0.0    1262    0        =
a contact +1562333 +1633801 base1  relay1 15mbit  0.0      22    0        =
a contact +1579235 +1611245 gs2    base1  30mbit  0.0    1261    0        =
a contact +1579252 +1613908 gs2    lgw    30mbit  0.0    1309    0        =
a contact +1579255 +1611167 gs2    relay2 30mbit  0.0    1281    0        =
a contact +1602643 +1648592 gs1    base1  30mbit  0.0    1265    0        =
a contact +1602966 +1637261 gs1    relay1 30mbit  0.0    1264    0        =
a contact +1605385 +1647878 gs1    lgw    30mbit  0.0    1319    0        =
a contact +1614427 +1698564 lgw    relay2 30mbit  0.0     225    0        =
a contact +1614810 +1976585 rover1 lgw    15mbit  0.0     215    0        =
a contact +1615970 +1640257 rover1 relay1 15mbit  0.0      47    0        =
a contact +1618769 +1682261 rover1 relay2 15mbit  0.0      19    0        =
a contact +1620537 +1691813 base1  relay2 15mbit  0.0      23    0        =
a contact +1639595 +1648623 gs1    relay1 30mbit  0.0    1272    0        =
a contact +1648717 +1720177 base1  relay1 15mbit  0.0      22    0        =
a contact +1668871 +1702502 gs2    lgw    30mbit  0.0    1339    0        =
a contact +1669644 +1699603 gs2    relay2 30mbit  0.0    1296    0        =
a contact +1669716 +1699801 gs2    base1  30mbit  0.0    1275    0        =
a contact +1691172 +1739011 gs1    base1  30mbit  0.0    1278    0        =
a contact +1691445 +1738987 gs1    relay1 30mbit  0.0    1273    0        =
a contact +1693922 +1737522 gs1    lgw    30mbit  0.0    1345    0        =
a contact +1700640 +1784804 lgw    relay2 30mbit  0.0     246    0        =
a contact +1706959 +1778224 base1  relay2 15mbit  0.0      23    0        =
a contact +1708190 +1726719 rover1 relay1 15mbit  0.0      42    0        =
a contact +1709135 +1775849 rover1 relay2 15mbit  0.0      27    0        =
a contact +1728244 +1814211 lgw    relay1 30mbit  0.0     245    0        =
a contact +1735098 +1806553 base1  relay1 15mbit  0.0      22    0        =
a contact +1758449 +1790936 gs2    lgw    30mbit  0.0    1354    0        =
a contact +1759981 +1788446 gs2    relay2 30mbit  0.0    1310    0        =
a contact +1760143 +1788706 gs2    base1  30mbit  0.0    1288    0        =
a contact +1780087 +1829231 gs1    base1  30mbit  0.0    1291    0        =
a contact +1780296 +1829147 gs1    relay1 30mbit  0.0    1281    0        =
a contact +1782309 +1827235 gs1    lgw    30mbit  0.0    1355    0        =
a contact +1786894 +1870983 lgw    relay2 30mbit  0.0     236    0        =
a contact +1793378 +1864631 base1  relay2 15mbit  0.0      23    0        =
a contact +1800753 +1813080 rover1 relay1 15mbit  0.0      34    0        =
a contact +1802479 +1866320 rover1 relay2 15mbit  0.0      38    0        =
a contact +1815236 +1900624 lgw    relay1 30mbit  0.0     225    0        =
a contact +1821477 +1892929 base1  relay1 15mbit  0.0      22    0        =
a contact +1848176 +1879326 gs2    lgw    30mbit  0.0    1353    0        =
a contact +1850114 +1877782 gs2    relay2 30mbit  0.0    1324    0        =
a contact +1850347 +1878035 gs2    base1  30mbit  0.0    1301    0        =
a contact +1869416 +1919121 gs1    base1  30mbit  0.0    1303    0        =
a contact +1869546 +1918976 gs1    relay1 30mbit  0.0    1290    0        =
a contact +1870679 +1917277 gs1    lgw    30mbit  0.0    1350    0        =
a contact +1873156 +1956923 lgw    relay2 30mbit  0.0     192    0        =
a contact +1879794 +1951033 base1  relay2 15mbit  0.0      23    0        =
a contact +1893372 +1899188 rover1 relay1 15mbit  0.0      22    0        =
a contact +1897595 +1954747 rover1 relay2 15mbit  0.0      47    0        =
a contact +1902124 +1987542 lgw    relay1 30mbit  0.0     169    0        =
a contact +1907855 +1979307 base1  relay1 15mbit  0.0      22    0        =
a contact +1938397 +1967765 gs2    lgw    30mbit  0.0    1337    0        =
a contact +1939881 +1967550 gs2    relay2 30mbit  0.0    1336    0        =
a contact +1940148 +1967776 gs2    base1  30mbit  0.0    1312    0        =
a contact +1959114 +2008576 gs1    base1  30mbit  0.0    1314    0        =
a contact +1959152 +2008854 gs1    lgw    30mbit  0.0    1331    0        =
a contact +1959159 +2008375 gs1    relay1 30mbit  0.0    1298    0        =
a contact +1959283 +2000347 lgw    relay2 30mbit  0.0     101    0        =
a contact +1966206 +2037429 base1  relay2 15mbit  0.0      23    0        =
a contact +1991708 +1998587 lgw    relay1 30mbit  0.0      48    0        =
a contact +1992315 +2042220 rover1 relay2 15mbit  0.0      52    0        =
a contact +1994233 +2065688 base1  relay1 15mbit  0.0      22    0        =
a contact +1999813 +2589853 lgw    relay1 30mbit  0.0      44    0        =
a contact +2002837 +2131461 lgw    relay2 30mbit  0.0      67    0        =
a contact +2010212 +2570192 base1  lgw    15mbit  0.0      31    0        =
a contact +2029184 +2057601 gs2    relay2 30mbit  0.0    1347    0        =
a contact +2029324 +2059296 gs2    lgw    30mbit  0.0    1330    0        =
a contact +2029449 +2057805 gs2    base1  30mbit  0.0    1322    0        =
a contact +2049038 +2097316 gs1    relay1 30mbit  0.0    1306    0        =
a contact +2049072 +2097559 gs1    base1  30mbit  0.0    1324    0        =
a contact +2050404 +2096445 gs1    lgw    30mbit  0.0    1340    0        =
a contact +2052613 +2123819 base1  relay2 15mbit  0.0      23    0        =
a contact +2080613 +2152074 base1  relay1 15mbit  0.0      22    0        =
a contact +2082481 +2455639 rover1 lgw    15mbit  0.0     142    0        =
a contact +2086036 +2129254 rover1 relay2 15mbit  0.0      54    0        =
a contact +2116869 +2149512 gs2    lgw    30mbit  0.0    1370    0        =
a contact +2118026 +2147751 gs2    relay2 30mbit  0.0    1356    0        =
a contact +2118264 +2147940 gs2    base1  30mbit  0.0    1331    0        =
a contact +2132588 +2217527 lgw    relay2 30mbit  0.0     195    0        =
a contact +2139014 +2210205 base1  relay2 15mbit  0.0      23    0        =
a contact +2139055 +2185830 gs1    relay1 30mbit  0.0    1313    0        =
a contact +2139146 +2186102 gs1    base1  30mbit  0.0    1333    0        =
a contact +2140758 +2184043 gs1    lgw    30mbit  0.0    1379    0        =
a contact +2166995 +2238464 base1  relay1 15mbit  0.0      22    0        =
a contact +2179021 +2216062 rover1 relay2 15mbit  0.0      54    0        =
a contact +2204571 +2239057 gs2    lgw    30mbit  0.0    1398    0        =
a contact +2206483 +2212806 gs2    relay2 30mbit  0.0    1363    0        =
a contact +2206686 +2238025 gs2    base1  30mbit  0.0    1339    0        =
a contact +2214935 +2237846 gs2    relay2 30mbit  0.0    1345    0        =
a contact +2219083 +2303755 lgw    relay2 30mbit  0.0     237    0        =
a contact +2225410 +2296587 base1  relay2 15mbit  0.0      23    0        =
a contact +2229102 +2273985 gs1    relay1 30mbit  0.0    1319    0        =
a contact +2229225 +2274279 gs1    base1  30mbit  0.0    1341    0        =
a contact +2230464 +2271695 gs1    lgw    30mbit  0.0    1403    0        =
a contact +2253379 +2324860 base1  relay1 15mbit  0.0      22    0        =
a contact +2271615 +2302741 rover1 relay2 15mbit  0.0      52    0        =
a contact +2292393 +2328336 gs2    lgw    30mbit  0.0    1410    0        =
a contact +2294659 +2298732 gs2    relay2 30mbit  0.0    1367    0        =
a contact +2294825 +2327974 gs2    base1  30mbit  0.0    1345    0        =
a contact +2302107 +2327805 gs2    relay2 30mbit  0.0    1349    0        =
a contact +2305572 +2390064 lgw    relay2 30mbit  0.0     247    0        =
a contact +2311801 +2382966 base1  relay2 15mbit  0.0      23    0        =
a contact +2319116 +2361860 gs1    relay1 30mbit  0.0    1324    0        =
a contact +2319249 +2362172 gs1    base1  30mbit  0.0    1346    0        =
a contact +2319925 +2359474 gs1    lgw    30mbit  0.0    1411    0        =
a contact +2334573 +2336904 rover1 relay1 15mbit  0.0       9    0        =
a contact +2339768 +2411261 base1  relay1 15mbit  0.0      22    0        =
a contact +2364061 +2389336 rover1 relay2 15mbit  0.0      48    0        =
a contact +2380396 +2417546 gs2    lgw    30mbit  0.0    1407    0        =
a contact +2382784 +2417773 gs2    base1  30mbit  0.0    1348    0        =
a contact +2388807 +2417617 gs2    relay2 30mbit  0.0    1353    0        =
a contact +2392096 +2476444 lgw    relay2 30mbit  0.0     227    0        =
a contact +2398187 +2469342 base1  relay2 15mbit  0.0      23    0        =
a contact +2409085 +2449528 gs1    relay1 30mbit  0.0    1327    0        =
a contact +2409215 +2449860 gs1    base1  30mbit  0.0    1349    0        =
a contact +2409319 +2447520 gs1    lgw    30mbit  0.0    1402    0        =
a contact +2420301 +2428793 rover1 relay1 15mbit  0.0       8    0        =
a contact +2426161 +2497668 base1  relay1 15mbit  0.0      22    0        =
a contact +2456481 +2475864 rover1 relay2 15mbit  0.0      43    0        =
a contact +2468719 +2506869 gs2    lgw    30mbit  0.0    1387    0        =
a contact +2470649 +2507451 gs2    base1  30mbit  0.0    1349    0        =
a contact +2475285 +2507313 gs2    relay2 30mbit  0.0    1354    0        =
a contact +2478695 +2563173 lgw    relay2 30mbit  0.0     173    0        =
a contact +2484569 +2555718 base1  relay2 15mbit  0.0      23    0        =
a contact +2498793 +2536185 gs1    lgw    30mbit  0.0    1376    0        =
a contact +2499032 +2537056 gs1    relay1 30mbit  0.0    1330    0        =
a contact +2499161 +2537412 gs1    base1  30mbit  0.0    1349    0        =
a contact +2506598 +2520577 rover1 relay1 15mbit  0.0       8    0        =
a contact +2512559 +2584079 base1  relay1 15mbit  0.0      22    0        =
a contact +2548835 +2562322 rover1 relay2 15mbit  0.0      35    0        =
a contact +2557817 +2592000 gs2    lgw    30mbit  0.0    1353    0        =
a contact +2558496 +2592000 gs2    base1  30mbit  0.0    1347    0        =
a contact +2561164 +2592000 gs2    relay2 30mbit  0.0    1355    0        =
a contact +2565564 +2592000 lgw    relay2 30mbit  0.0      58    0        =
a contact +2570948 +2592000 base1  relay2 15mbit  0.0      23    0        =
a contact +2588911 +2592000 base1  lgw    15mbit  0.0      27    0        =
