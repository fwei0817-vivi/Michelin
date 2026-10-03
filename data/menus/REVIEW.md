# Menu review checklist

Check each dish against the restaurant's menu, fix labels in the menu JSON (or in the app's menu editor), then set `"verified": true`. Unknown stays unknown when the menu does not say: ask the restaurant rather than guess.

## Atlas Kitchen (`atlas_kitchen`)

### 1. Not recognized (12): fill ingredients and diet flags by hand
- [ ] **Spicy Dried Tofu 钱来山秘制湘干 ($9.95)**: no description
- [ ] **Spinach with White Sesame 芝麻菠菜 ($8.95)**: no description
- [ ] **Cucumber Salad with Garlic Sauce 绝味黄瓜 ($8.95)**: no description
- [ ] **Preserved Egg with Green and Red Peppers 双椒皮蛋 ($10.95)**: no description
- [ ] **Crab with Pork Soup Dumplings (6Pc) 蟹粉小笼包 ($11.95)**: no description
- [ ] **Sautéed Pork with Hot Pepper 山海辣椒小炒肉 ($17.95)**: no description
- [ ] **Creamy Prawn with Walnut 奶油核桃虾 ($28.95)**: no description
- [ ] **Sautéed Bok Choy 青丘素菜钵 ($16.95)**: no description
- [ ] **Sautéed Sliced Eggplant with Chili 山海烧茄子 ($17.95)**: no description
- [ ] **Sautéed Sliced Wintermelon with Spam 火腿冬瓜片 ($17.95)**: no description
- [ ] **Organic Cauliflower in Drywok Flavored with Sliced Pork 干锅有机花菜 ($18.95)**: no description
- [ ] **Broccoli with Garlic Sauce 鱼香芥兰 ($15.95)**: no description

### 2. Matched by the LLM (7): confirm it is the same dish
- [ ] **Shanghai Crispy Spring Rolls (4Pc) 上海春卷 ($5.95)** read as `vegetable_spring_rolls`: egg (unknown); soy (unknown); wheat (inferred)
- [ ] **Sautéed Cumin Flavor Sliced Lamb 孜然黑山羊 ($23.95)** read as `cumin_lamb`: not vegetarian; soy (inferred); wheat (inferred)
- [ ] **Chicken with Red Dried Chili 歌乐山辣子鸡 ($22.95)** read as `chongqing_chicken`: not vegetarian; peanut (unknown); sesame (unknown); soy (inferred); wheat (inferred)
- [ ] **Scramble Egg & Chopped Tomato 山海番茄炒鸡蛋 ($16.95)** read as `tomato_egg`: not vegetarian; egg (menu)
- [ ] **Fish Filet in Chili Oil 江北水煮鱼 ($22.95)** read as `boiled_fish`: not vegetarian; fish (menu); soy (inferred); wheat (inferred)
- [ ] **Braised Fish Fillet with Chinese Sauerkraut 特色酸菜鱼 ($23.95)** read as `pickled_cabbage_fish`: not vegetarian; egg (unknown); fish (menu)
- [ ] **Dan Dan Noodle 会稽山担担面 ($8.95)** read as `dan_dan_noodles`: not vegetarian; peanut (inferred); sesame (inferred); soy (inferred); wheat (menu)

### 3. Restaurant tags disagree with labels (0)
- none

### 4. Recognized (21): spot-check against the menu
- [ ] Mouth-watering Chicken 红油口水鸡 ($12.95): not vegetarian; peanut (inferred); sesame (inferred); soy (inferred); wheat (inferred)
- [ ] Sliced Pork Belly with Garlic Sauce 祗山晾衣白肉 ($11.95): not vegetarian; sesame (unknown); soy (inferred); wheat (inferred)
- [ ] Scallion Pancake 葱油饼 ($6.95): soy (inferred); wheat (inferred)
- [ ] Pork Potstickers (6Pc) 锅贴 ($8.95): not vegetarian; sesame (unknown); soy (inferred); wheat (inferred)
- [ ] Egg Drop with Seaweed Soup (Per Person) 紫菜蛋花汤 ($3.95): not vegetarian; egg (menu)
- [ ] Hot and Sour Soup (Per Person) 酸辣汤 ($3.95): not vegetarian; egg (inferred); soy (inferred); wheat (inferred)
- [ ] Crispy Pork in Sweet & Sour Sauce 锅包肉 ($18.95): not vegetarian; egg (inferred); wheat (inferred)
- [ ] Sautéed Chinese Bacon with Garlic Sprouts 蒜苗腊肉 ($19.95): not vegetarian; soy (inferred); wheat (inferred)
- [ ] Braised Pork Belly 岷山红烧肉 ($18.95): not vegetarian; soy (inferred); wheat (inferred)
- [ ] Scrambled Eggs with Shrimp 滑蛋虾仁 ($16.95): not vegetarian; egg (menu); shellfish (menu)
- [ ] Stir-fried String Beans 干煸四季豆 ($16.95): not vegetarian; shellfish (unknown); soy (inferred); wheat (inferred)
- [ ] Stir-fried Shredded Potatoes 酸辣土豆丝 ($15.95): nothing flagged
- [ ] Sautéed Potato, Green Pepper & Eggplant 地三鲜 ($16.95): shellfish (unknown); soy (inferred); wheat (inferred)
- [ ] Stir-fried Cabbage 炝炒包菜 ($15.95): soy (unknown); wheat (unknown)
- [ ] Mapo Tofu 麻婆豆腐 ($15.95): not vegetarian; soy (menu); wheat (inferred)
- [ ] Yang Chow Fried Rice (Shrimp, Spam, Scrambled Eggs, Mushroom) 扬州炒饭 ($13.95): not vegetarian; egg (menu); shellfish (menu); soy (inferred); wheat (inferred)
- [ ] Steamed White Rice 白饭 ($1.5): nothing flagged
- [ ] General Tso's Chicken 左宗棠鸡 ($16.95): not vegetarian; egg (inferred); soy (inferred); wheat (inferred)
- [ ] Beef with Broccoli 芥兰牛 ($19.95): not vegetarian; shellfish (inferred); soy (inferred); wheat (inferred)
- [ ] Shredded Pork with Garlic Sauce 鱼香肉丝 ($16.95): not vegetarian; soy (inferred); wheat (inferred)
- [ ] Kung Pao Chicken 宫保鸡丁 ($16.95): not vegetarian; peanut (inferred); soy (inferred); wheat (inferred)

## Café China (`cafe_china`)

### 1. Not recognized (14): fill ingredients and diet flags by hand
- [ ] **House Smoked Tofu 香薰豆腐 ($12)**: Smoked tofu, peanuts, fermented soybean, [V]
- [ ] **Poached Okras 捞汁秋葵 ($14)**: Tabasco peppers, sesame oil, [V]
- [ ] **Cold Noodles with Shredded Chicken 鸡丝凉⾯ ($12)**: Wheat noodles, chicken, chili oil, peanuts, sesame
- [ ] **Spicy Cucumbers 醋熏瓜条 ($12)**: Cucumbers, chili peppers, Sichuan peppercorns, [V]
- [ ] **Chive Pancakes (2) 韭菜盒子 ($12)**: Dried shrimp, egg
- [ ] **Shanghai Shumai (4) 上海烧卖 ($10)**: Sticky rice, Chinese pork sausages, salted egg yolk, shiitake mushrooms
- [ ] **Spicy Soft Shell Crabs 香辣软壳蟹 ($38)**: Soft shell crabs, cayenne peppers, Sichuan peppercorns, garlic, wheat flour
- [ ] **Spicy Fish Fillets 香辣鱼片 ($24)**: Sole fish, cayenne peppers, Sichuan peppercorns, cilantro
- [ ] **Braised Pork Szechuan Style 豆花咸烧白 ($22)**: Pork belly, tofu, fermented mustard greens shoots, fish sauce
- [ ] **Curiously Tasty Chicken 奇味鸡 ($24)**: Chicken, winter melon, cumin, oyster sauce, fish sauce, basil
- [ ] **Loofah with Dried Scallops 丝瓜扇贝 ($24)**: Loofah, dried scallops
- [ ] **Eggplants and String Beans 四川双素 ($19)**: Eggplants, string beans, oyster sauce
- [ ] **Poached Snow Pea Shoots 上汤豆苗 ($22)**: Snow pea shoots, oyster mushrooms, dried shrimp, dried scallops, [GF]
- [ ] **Fried Rice with Shredded Duck 樟茶鸭丝炒饭 ($17)**: Rice, egg, shredded duck, onion, [GF]

### 2. Matched by the LLM (6): confirm it is the same dish
- [ ] **Sweet & Sour Baby Ribs 糖醋小排 ($12)** read as `sweet_sour_pork`: not vegetarian; egg (inferred); sesame (menu); wheat (inferred)
- [ ] **Pork in Garlic Dressing 蒜泥白肉卷 ($16)** read as `garlic_pork_belly`: not vegetarian; sesame (unknown); soy (inferred); wheat (inferred)
- [ ] **Pork Pot Stickers (4) 鲜肉锅贴 ($10)** read as `pork_dumplings`: not vegetarian; sesame (unknown); soy (inferred); wheat (inferred)
- [ ] **Kung Fu Shrimp 飞鸿大虾 ($32)** read as `kung_pao_shrimp`: not vegetarian; peanut (menu); sesame (menu); shellfish (menu); soy (inferred); wheat (inferred)
- [ ] **Three Pepper Chicken 三椒煸鸡 ($22)** read as `chongqing_chicken`: not vegetarian; peanut (unknown); sesame (unknown); soy (inferred); wheat (inferred)
- [ ] **Spicy Cumin Lamb 香辣孜然羊 ($31)** read as `cumin_lamb`: not vegetarian; soy (inferred); wheat (inferred)

### 3. Restaurant tags disagree with labels (1)
- [ ] **Ma Po Tofu 麻婆豆腐 ($19)**: restaurant marks it vegetarian; labels say not.

### 4. Recognized (20): spot-check against the menu
- [ ] Mouth Watering Chicken ⼝⽔鸡 ($16): not vegetarian; peanut (menu); sesame (menu); soy (inferred); wheat (inferred)
- [ ] Husband & Wife Special 夫妻肺⽚ ($16): not vegetarian; peanut (menu); sesame (menu); soy (inferred); wheat (inferred)
- [ ] Wonton Soup 原汤馄饨 ($10): not vegetarian; egg (unknown); shellfish (inferred); wheat (inferred)
- [ ] Crystal Shrimp Dumplings (4) 水晶虾饺 ($12): not vegetarian; shellfish (menu); wheat (menu)
- [ ] Vegetable Pot Stickers (4) 素菜贴 ($12): egg (unknown); soy (menu); wheat (inferred)
- [ ] Pork Soup Dumplings (4) 小笼汤包 ($10): not vegetarian; soy (inferred); wheat (menu)
- [ ] Scallion Pancakes 葱油饼 ($8): soy (inferred); wheat (inferred)
- [ ] Dan Dan Noodles 担担面 ($12): not vegetarian; peanut (inferred); sesame (menu); soy (inferred); wheat (menu)
- [ ] Pork Dumplings in Chili Oil (8) 红油水饺 ($10): not vegetarian; sesame (inferred); soy (inferred); wheat (menu)
- [ ] Tea Smoked Duck 樟茶鸭 ($20): not vegetarian; soy (inferred); wheat (menu)
- [ ] Kung Pao Chicken 宫保鸡丁 ($20): not vegetarian; peanut (menu); soy (inferred); wheat (inferred)
- [ ] Chungking Spicy Chicken 重庆辣子鸡 ($25): not vegetarian; peanut (unknown); sesame (menu); soy (inferred); wheat (inferred)
- [ ] Shredded Beef with Green Chili 小椒牛肉 ($24): not vegetarian; shellfish (unknown); soy (inferred); wheat (inferred)
- [ ] Ma Po Tofu 麻婆豆腐 ($19): not vegetarian; soy (menu); wheat (inferred)
- [ ] Shredded Pork in Garlic Sauce 魚香肉絲 ($20): not vegetarian; soy (inferred); wheat (inferred)
- [ ] Double Cooked Pork 回锅肉 ($25): not vegetarian; soy (inferred); wheat (inferred)
- [ ] Stir-fried Cabbage 手撕包菜 ($17): soy (unknown); wheat (unknown)
- [ ] Eggplants in Garlic Sauce 鱼香茄子 ($18): soy (inferred); wheat (inferred)
- [ ] Shrimp Fried Rice with Chinese Sausage 虾仁炒饭 ($17): not vegetarian; egg (menu); shellfish (menu); soy (inferred); wheat (inferred)
- [ ] White Rice 白饭 ($2): nothing flagged

## CHILI (`chili`)

### 1. Not recognized (9): fill ingredients and diet flags by hand
- [ ] **Cucumber Salad  ($12)**: diced cucumber with house-made garlic dressing GF V
- [ ] **Poached Okra 漩汁秋葵 ($14)**: no description
- [ ] **Beef Pancake Wrap  ($16)**: hand-kneaded crispy scallion pancake wrapped around tender braised beef shank with our special sauce spread, onion, and cilantro
- [ ] **Braised Tofu with Crab Meat  ($35)**: stewed crab roe and tofu
- [ ] **Fragrant Fish Fillet  ($26)**: fillet of sole with seasonal vegetables and green chili pepper, soy sauce
- [ ] **Fried Rice with Preserved Vegetable  ($15)**: no description
- [ ] **Sautéed Potato Shreds  ($18)**: no description
- [ ] **Sautéed Chinese Broccoli  ($18)**: [GF]
- [ ] **Dry-pot Cabbage  ($19)**: no description

### 2. Matched by the LLM (9): confirm it is the same dish
- [ ] **Szechuan Cold Noodle  ($12)** read as `sesame_cold_noodles`: peanut (menu); sesame (menu); soy (inferred); wheat (menu)
- [ ] **Pork in Garlic Dressing  ($15)** read as `garlic_pork_belly`: not vegetarian; sesame (unknown); soy (menu); wheat (inferred)
- [ ] **Pork Pot Stickers (6 pcs)  ($12)** read as `pork_dumplings`: not vegetarian; sesame (unknown); soy (inferred); wheat (inferred)
- [ ] **Chungking Spicy Chicken  ($28)** read as `chongqing_chicken`: not vegetarian; peanut (unknown); sesame (unknown); soy (inferred); wheat (inferred)
- [ ] **Pickled Fish Stew  ($38)** read as `pickled_cabbage_fish`: not vegetarian; egg (unknown); fish (menu)
- [ ] **Red Style Chungking Braised Fish Stew  ($38)** read as `boiled_fish`: not vegetarian; fish (menu); soy (inferred); wheat (inferred)
- [ ] **Kung Fu Shrimp  ($36)** read as `kung_pao_shrimp`: not vegetarian; peanut (menu); shellfish (menu); soy (inferred); wheat (inferred)
- [ ] **Spicy Cumin Lamb  ($32)** read as `cumin_lamb`: not vegetarian; soy (inferred); wheat (inferred)
- [ ] **Sautéed String Beans  ($21)** read as `dry_fried_string_beans`: not vegetarian; shellfish (unknown); soy (inferred); wheat (inferred)

### 3. Restaurant tags disagree with labels (1)
- [ ] **Ma Po Tofu  ($22)**: restaurant marks it vegetarian; labels say not.

### 4. Recognized (22): spot-check against the menu
- [ ] Mr. and Mrs. Smith  ($16): not vegetarian; peanut (menu); sesame (inferred); soy (inferred); wheat (inferred)
- [ ] Mouth Watering Chicken  ($14): not vegetarian; peanut (menu); sesame (menu); soy (inferred); wheat (inferred)
- [ ] Mung Bean Jelly  ($12): peanut (unknown); sesame (menu); soy (menu); wheat (menu)
- [ ] Five Spice Beef  ($14): not vegetarian; soy (inferred); wheat (inferred)
- [ ] Scallion Pancakes (6 pcs)  ($10): soy (inferred); wheat (inferred)
- [ ] Crystal Shrimp Dumplings (5 pcs)  ($12): not vegetarian; shellfish (menu); wheat (menu)
- [ ] Vegetable Pot Stickers (6 pcs)  ($12): egg (unknown); soy (inferred); wheat (inferred)
- [ ] Pork Dumplings in Chili Oil (6 pcs)  ($12): not vegetarian; sesame (inferred); soy (inferred); wheat (menu)
- [ ] Spicy Wonton (6 pcs)  ($12): not vegetarian; egg (unknown); peanut (unknown); sesame (unknown); soy (inferred); wheat (inferred)
- [ ] Wonton Soup  ($12): not vegetarian; egg (unknown); shellfish (inferred); wheat (inferred)
- [ ] Dan Dan Noodles  ($12): not vegetarian; peanut (inferred); sesame (menu); soy (inferred); wheat (menu)
- [ ] Shredded Beef with Green Chili  ($28): not vegetarian; shellfish (unknown); soy (inferred); wheat (inferred)
- [ ] Tea Smoked Duck  ($35): not vegetarian; soy (inferred); wheat (inferred)
- [ ] Shredded Pork in Garlic Sauce  ($24): not vegetarian; soy (inferred); wheat (inferred)
- [ ] Twice Cooked Pork  ($24): not vegetarian; soy (menu); wheat (inferred)
- [ ] Ma Po Tofu  ($22): not vegetarian; soy (menu); wheat (inferred)
- [ ] Kung Pao Chicken  ($25): not vegetarian; peanut (menu); soy (inferred); wheat (inferred)
- [ ] Kung Pao Shrimp 宫保虾仁 ($34): not vegetarian; peanut (inferred); shellfish (menu); soy (inferred); wheat (inferred)
- [ ] Shrimp Fried Rice 虾炒饭 ($20): not vegetarian; egg (inferred); shellfish (menu); soy (inferred); wheat (inferred)
- [ ] White Rice  ($2): nothing flagged
- [ ] Eggplant in Garlic Sauce  ($19): soy (inferred); wheat (inferred)
- [ ] Bok Choy with Garlic  ($18): shellfish (unknown)
