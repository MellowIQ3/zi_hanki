import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from dotenv import load_dotenv
from keep_alive import keep_alive

keep_alive()  

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
DATA_FILE = "jihanki.json"
APPROVAL_CHANNEL_ID = int(os.getenv("APPROVAL_CHANNEL_ID", 0))
ACHIEVEMENT_CHANNEL_ID = int(os.getenv("ACHIEVEMENT_CHANNEL_ID", 0))

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump({}, f)

def load_data():
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

class JihankiBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        intents.guilds = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        print("✅ Slash commands synced")

bot = JihankiBot()

# 在庫変更時に自販機メッセージを更新する関数
async def update_jihanki_messages(jihanki_name):
    data = load_data()
    
    # メッセージIDが保存されていない場合は何もしない
    if jihanki_name not in data or "message_ids" not in data[jihanki_name]:
        return
        
    for msg_info in data[jihanki_name]["message_ids"]:
        try:
            channel_id = msg_info["channel_id"]
            message_id = msg_info["message_id"]
            
            channel = bot.get_channel(channel_id)
            if not channel:
                channel = await bot.fetch_channel(channel_id)
                
            message = await channel.fetch_message(message_id)
            
            # 埋め込みを更新
            embed = discord.Embed(
                title=f"🏪 {jihanki_name}",
                description="下のボタンから商品を購入できます",
                color=discord.Color.blue()
            )
            
            # 商品情報を価格順にソート
            items = []
            for item, info in data[jihanki_name].items():
                if isinstance(info, dict) and "price" in info:
                    items.append((item, info))
            
            # 価格順に並べ替え
            items.sort(key=lambda x: x[1]["price"])
            
            # 商品を下に表示
            for item, info in items:
                # 在庫状況に応じた絵文字
                if info['stock'] <= 0:
                    stock_status = "❌ 在庫切れ"
                elif info['stock'] < 5:
                    stock_status = f"⚠️ 残り{info['stock']}個"
                else:
                    stock_status = f"✅ 在庫あり ({info['stock']}個)"
                    
                # 価格表示
                if info['price'] == 0:
                    price_display = "🆓 無料"
                else:
                    price_display = f"💰 {info['price']}円"
                    
                embed.add_field(
                    name=item,
                    value=f"{price_display}\n{stock_status}",
                    inline=True
                )
                
            embed.set_footer(text=f"最終更新: {discord.utils.utcnow().strftime('%Y/%m/%d %H:%M:%S')}")
            
            await message.edit(embed=embed)
        except Exception as e:
            print(f"メッセージ更新エラー: {e}")
            continue

class SelectItemToPurchase(discord.ui.Select):
    def __init__(self, jihanki_name):
        self.jihanki_name = jihanki_name
        data = load_data()
        
        # 商品ごとに在庫状況に応じた絵文字を追加
        options = []
        
        # データ構造のチェックと商品情報の取得
        if jihanki_name in data:
            for item, info in data[jihanki_name].items():
                # message_idsキーはスキップ
                if item == "message_ids":
                    continue
                    
                # 辞書かどうか確認し、必要なキーが存在するか確認
                if isinstance(info, dict) and "stock" in info and "price" in info:
                    # 在庫状況に応じた絵文字を設定
                    if info['stock'] <= 0:
                        emoji = "❌"
                        description = f"在庫切れ | {info['price']}円"
                    elif info['stock'] < 5:
                        emoji = "⚠️"
                        description = f"残り{info['stock']}個 | {info['price']}円"
                    else:
                        emoji = "✅"
                        description = f"在庫あり ({info['stock']}個) | {info['price']}円"
                        
                    options.append(
                        discord.SelectOption(
                            label=item,
                            value=item,
                            description=description,
                            emoji=emoji
                        )
                    )
        
        # オプションが空の場合はダミーオプションを追加
        if not options:
            options.append(
                discord.SelectOption(
                    label="商品がありません",
                    value="no_items",
                    description="この自販機には商品がありません",
                    emoji="❌"
                )
            )
            
        super().__init__(
            placeholder="🛒 購入する商品を選んでください",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        item = self.values[0]
        
        # 商品がない場合の処理
        if item == "no_items":
            await interaction.response.send_message("❌ この自販機には商品がありません。", ephemeral=True)
            return
            
        data = load_data()
        
        # データ構造の確認
        if self.jihanki_name not in data or item not in data[self.jihanki_name]:
            await interaction.response.send_message("❌ 商品情報が見つかりません。", ephemeral=True)
            return
            
        if not isinstance(data[self.jihanki_name][item], dict) or "stock" not in data[self.jihanki_name][item]:
            await interaction.response.send_message("❌ 商品情報が正しくありません。", ephemeral=True)
            return
            
        stock = data[self.jihanki_name][item]["stock"]
        
        if stock <= 0:
            await interaction.response.send_message("❌ 在庫切れです。", ephemeral=True)
            return
            
        price = data[self.jihanki_name][item]["price"]
        
        if price == 0:
            # 価格が0円の場合は直接DMに送信
            await self.process_purchase(interaction, item, None)
        else:
            # 価格が0円でない場合はPayPayリンク入力モーダルを表示
            await interaction.response.send_modal(PayPayLinkModal(self.jihanki_name, item))

    async def process_purchase(self, interaction, item, paypay_link=None):
        data = load_data()
        data[self.jihanki_name][item]["stock"] -= 1
        save_data(data)
        
        # 自販機メッセージを更新
        await update_jihanki_messages(self.jihanki_name)
        
        # 価格に応じた色を設定
        if data[self.jihanki_name][item]['price'] == 0:
            embed_color = discord.Color.green()  # 無料商品は緑色
        elif data[self.jihanki_name][item]['price'] < 500:
            embed_color = discord.Color.blue()   # 安価な商品は青色
        elif data[self.jihanki_name][item]['price'] < 1000:
            embed_color = discord.Color.gold()   # 中価格帯は金色
        else:
            embed_color = discord.Color.purple() # 高価格帯は紫色
        
        # DMに送信する内容
        embed = discord.Embed(
            title="🎉 購入完了", 
            description=f"**{item}** を購入しました！", 
            color=embed_color
        )
        embed.add_field(name="💰 価格", value=f"{data[self.jihanki_name][item]['price']}円")
        embed.add_field(name="📦 残り在庫", value=f"{data[self.jihanki_name][item]['stock']}")
        
        # DMに送信する商品情報があれば追加
        if "dm_content" in data[self.jihanki_name][item] and data[self.jihanki_name][item]["dm_content"]:
            embed.add_field(name="📝 商品情報", value=data[self.jihanki_name][item]["dm_content"], inline=False)
        
        # フッターに購入日時を追加
        embed.set_footer(text=f"購入日時: {discord.utils.utcnow().strftime('%Y/%m/%d %H:%M:%S')}")
        
        await interaction.user.send(embed=embed)
        
        # 実績チャンネルに送信
        if ACHIEVEMENT_CHANNEL_ID:
            achievement_channel = bot.get_channel(ACHIEVEMENT_CHANNEL_ID)
            if achievement_channel:
                achievement_embed = discord.Embed(
                    title="🛍️ 購入実績", 
                    description=f"{interaction.user.mention} が **{item}** を購入しました！", 
                    color=embed_color
                )
                achievement_embed.add_field(name="💰 価格", value=f"{data[self.jihanki_name][item]['price']}円")
                achievement_embed.add_field(name="📦 残り在庫", value=f"{data[self.jihanki_name][item]['stock']}")
                await achievement_channel.send(embed=achievement_embed)
        
        await interaction.response.send_message("✅ DMに購入情報を送りました。", ephemeral=True)

class PayPayLinkModal(discord.ui.Modal, title="PayPay決済リンク入力"):
    paypay_link = discord.ui.TextInput(label="PayPayリンク", placeholder="https://pay.paypay.ne.jp/...")
    
    def __init__(self, jihanki_name, item):
        super().__init__()
        self.jihanki_name = jihanki_name
        self.item = item
        
    async def on_submit(self, interaction: discord.Interaction):
        link = self.paypay_link.value.strip()
        
        if not link.startswith("https://pay.paypay.ne.jp/"):
            await interaction.response.send_message("❌ 有効なPayPayリンクを入力してください。", ephemeral=True)
            return
            
        # 承認チャンネルに送信
        if APPROVAL_CHANNEL_ID:
            approval_channel = bot.get_channel(APPROVAL_CHANNEL_ID)
            if approval_channel:
                data = load_data()
                embed = discord.Embed(
                    title="💳 購入承認リクエスト", 
                    description=f"{interaction.user.mention} が **{self.item}** を購入しようとしています。", 
                    color=discord.Color.blue()
                )
                embed.add_field(name="💰 価格", value=f"{data[self.jihanki_name][self.item]['price']}円")
                embed.add_field(name="🔗 PayPayリンク", value=link)
                
                view = ApprovalView(self.jihanki_name, self.item, interaction.user.id, link)
                await approval_channel.send(embed=embed, view=view)
                await interaction.response.send_message("✅ 決済リクエストを送信しました。承認されるまでお待ちください。", ephemeral=True)
            else:
                await interaction.response.send_message("❌ 承認チャンネルが見つかりません。管理者に連絡してください。", ephemeral=True)
        else:
            await interaction.response.send_message("❌ 承認チャンネルが設定されていません。管理者に連絡してください。", ephemeral=True)

class ApprovalView(discord.ui.View):
    def __init__(self, jihanki_name, item, user_id, paypay_link):
        super().__init__(timeout=None)
        self.jihanki_name = jihanki_name
        self.item = item
        self.user_id = user_id
        self.paypay_link = paypay_link
        
    @discord.ui.button(label="✅ 承認", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        data[self.jihanki_name][self.item]["stock"] -= 1
        save_data(data)
        
        # 自販機メッセージを更新
        await update_jihanki_messages(self.jihanki_name)
        
        user = await bot.fetch_user(self.user_id)
        
        # 価格に応じた色を設定
        if data[self.jihanki_name][self.item]['price'] == 0:
            embed_color = discord.Color.green()
        elif data[self.jihanki_name][self.item]['price'] < 500:
            embed_color = discord.Color.blue()
        elif data[self.jihanki_name][self.item]['price'] < 1000:
            embed_color = discord.Color.gold()
        else:
            embed_color = discord.Color.purple()
        
        # DMに送信
        embed = discord.Embed(
            title="🎉 購入完了", 
            description=f"**{self.item}** を購入しました！", 
            color=embed_color
        )
        embed.add_field(name="💰 価格", value=f"{data[self.jihanki_name][self.item]['price']}円")
        embed.add_field(name="📦 残り在庫", value=f"{data[self.jihanki_name][self.item]['stock']}")
        
        # DMに送信する商品情報があれば追加
        if "dm_content" in data[self.jihanki_name][self.item] and data[self.jihanki_name][self.item]["dm_content"]:
            embed.add_field(name="📝 商品情報", value=data[self.jihanki_name][self.item]["dm_content"], inline=False)
        
        # フッターに購入日時を追加
        embed.set_footer(text=f"購入日時: {discord.utils.utcnow().strftime('%Y/%m/%d %H:%M:%S')}")
        
        await user.send(embed=embed)
        
        # 実績チャンネルに送信
        if ACHIEVEMENT_CHANNEL_ID:
            achievement_channel = bot.get_channel(ACHIEVEMENT_CHANNEL_ID)
            if achievement_channel:
                achievement_embed = discord.Embed(
                    title="🛍️ 購入実績", 
                    description=f"<@{self.user_id}> が **{self.item}** を購入しました！", 
                    color=embed_color
                )
                achievement_embed.add_field(name="💰 価格", value=f"{data[self.jihanki_name][self.item]['price']}円")
                achievement_embed.add_field(name="👤 承認者", value=interaction.user.mention)
                await achievement_channel.send(embed=achievement_embed)
        
        # ボタンを無効化
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(content="✅ 購入が承認されました", view=self)
        
    @discord.ui.button(label="❌ 拒否", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = await bot.fetch_user(self.user_id)
        await user.send(f"❌ **{self.item}** の購入が拒否されました。")
        
        # ボタンを無効化
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(content="❌ 購入が拒否されました", view=self)

class PurchaseButton(discord.ui.View):
    def __init__(self, jihanki_name):
        super().__init__(timeout=None)
        self.jihanki_name = jihanki_name
        self.add_item(discord.ui.Button(label="🛒 購入する", style=discord.ButtonStyle.primary, custom_id=f"purchase_{jihanki_name}"))
        
    async def interaction_check(self, interaction: discord.Interaction):
        custom_id = interaction.data.get("custom_id", "")
        if custom_id.startswith("purchase_"):
            jihanki_name = custom_id.split("_")[1]
            
            # データの存在確認
            data = load_data()
            if jihanki_name not in data:
                await interaction.response.send_message("❌ この自販機は存在しません。", ephemeral=True)
                return True
                
            view = discord.ui.View()
            view.add_item(SelectItemToPurchase(jihanki_name))
            await interaction.response.send_message("🛒 購入する商品を選んでください：", view=view, ephemeral=True)
        return True

class AddJihankiModal(discord.ui.Modal, title="自販機追加"):
    name = discord.ui.TextInput(label="自販機名", placeholder="例: 飲料自販機")

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        name = self.name.value.strip()
        if not name:
            await interaction.response.send_message("❌ 名前を入力してください。", ephemeral=True)
            return
        if name in data:
            await interaction.response.send_message("❌ 既に存在します。", ephemeral=True)
        else:
            data[name] = {}
            save_data(data)
            await interaction.response.send_message(f"✅ '{name}' を追加しました！", ephemeral=True)

class AddItemModal(discord.ui.Modal, title="商品追加"):
    name = discord.ui.TextInput(label="商品名", placeholder="例: コーラ")
    stock = discord.ui.TextInput(label="在庫数", placeholder="例: 10")
    price = discord.ui.TextInput(label="価格", placeholder="例: 150")
    dm_content = discord.ui.TextInput(label="商品情報", placeholder="DMに送信する商品情報", required=False, style=discord.TextStyle.paragraph)

    def __init__(self, jihanki_name):
        super().__init__()
        self.jihanki_name = jihanki_name

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        item = self.name.value.strip()
        if not item:
            await interaction.response.send_message("❌ 商品名を入力してください。", ephemeral=True)
            return
        try:
            stock = int(self.stock.value)
            price = int(self.price.value)
        except ValueError:
            await interaction.response.send_message("❌ 数値を入力してください。", ephemeral=True)
            return
        
        # DMに送信する商品情報を追加
        dm_content = self.dm_content.value.strip() if self.dm_content.value else ""
        
        data[self.jihanki_name][item] = {
            "stock": stock, 
            "price": price,
            "dm_content": dm_content
        }
        save_data(data)
        
        # 自販機メッセージを更新
        await update_jihanki_messages(self.jihanki_name)
        
        await interaction.response.send_message(f"✅ '{item}' を '{self.jihanki_name}' に追加しました。", ephemeral=True)

class ChangeStockModal(discord.ui.Modal, title="在庫変更"):
    stock = discord.ui.TextInput(label="新しい在庫数", placeholder="例: 15")

    def __init__(self, jihanki, item):
        super().__init__()
        self.jihanki = jihanki
        self.item = item

    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_stock = int(self.stock.value)
        except ValueError:
            await interaction.response.send_message("❌ 有効な数値を入力してください。", ephemeral=True)
            return
        data = load_data()
        data[self.jihanki][self.item]["stock"] = new_stock
        save_data(data)
        
        # 自販機メッセージを更新
        await update_jihanki_messages(self.jihanki)
        
        await interaction.response.send_message(f"✅ '{self.item}' の在庫を {new_stock} に更新しました。", ephemeral=True)

class SelectItem(discord.ui.View):
    def __init__(self, jihanki, action):
        super().__init__()
        self.jihanki = jihanki
        self.action = action
        data = load_data()
        
        # 商品ごとに在庫状況に応じた絵文字を追加
        options = []
        
        if jihanki in data:
            for item, info in data[jihanki].items():
                # message_idsキーはスキップ
                if item == "message_ids":
                    continue
                    
                # 辞書かどうか確認し、必要なキーが存在するか確認
                if isinstance(info, dict) and "stock" in info and "price" in info:
                    # 在庫状況に応じた絵文字を設定
                    if info['stock'] <= 0:
                        emoji = "❌"
                        description = f"在庫切れ | {info['price']}円"
                    elif info['stock'] < 5:
                        emoji = "⚠️"
                        description = f"残り{info['stock']}個 | {info['price']}円"
                    else:
                        emoji = "✅"
                        description = f"在庫あり ({info['stock']}個) | {info['price']}円"
                        
                    options.append(
                        discord.SelectOption(
                            label=item,
                            value=item,
                            description=description,
                            emoji=emoji
                        )
                    )
        
        # オプションが空の場合はダミーオプションを追加
        if not options:
            options.append(
                discord.SelectOption(
                    label="商品がありません",
                    value="no_items",
                    description="この自販機には商品がありません",
                    emoji="❌"
                )
            )
            
        select = discord.ui.Select(
            placeholder="商品を選んでください",
            options=options,
            min_values=1,
            max_values=1
        )
        select.callback = self.item_callback
        self.add_item(select)

    async def item_callback(self, interaction: discord.Interaction):
        item = interaction.data['values'][0]
        data = load_data()

        if self.action == "remove":
            if item in data[self.jihanki]:
                del data[self.jihanki][item]
                save_data(data)
                
                # 自販機メッセージを更新
                await update_jihanki_messages(self.jihanki)
                
                await interaction.response.send_message(f"🗑 '{item}' を削除しました。", ephemeral=True)
            else:
                await interaction.response.send_message("❌ 商品が見つかりません。", ephemeral=True)

        elif self.action == "stock":
            await interaction.response.send_modal(ChangeStockModal(self.jihanki, item))

class ChannelSelector(discord.ui.View):
    def __init__(self, jihanki):
        super().__init__()
        self.jihanki = jihanki
        select = discord.ui.ChannelSelect(channel_types=[discord.ChannelType.text])
        select.callback = self.select_channel
        self.add_item(select)

    async def select_channel(self, interaction: discord.Interaction):
        channel_id = interaction.data['values'][0]
        channel = await bot.fetch_channel(int(channel_id))
        
        # 自販機メッセージを送信し、メッセージIDを保存
        message = await channel.send(embed=self.build_embed(), view=PurchaseButton(self.jihanki))
        
        # メッセージIDを保存
        data = load_data()
        if "message_ids" not in data[self.jihanki]:
            data[self.jihanki]["message_ids"] = []
        
        data[self.jihanki]["message_ids"].append({
            "channel_id": channel.id,
            "message_id": message.id
        })
        save_data(data)
        
        await interaction.response.send_message("✅ 自販機を送信しました。在庫変更時に自動更新されます。", ephemeral=True)

    def build_embed(self):
        data = load_data()[self.jihanki]
        embed = discord.Embed(
            title=f"🏪 {self.jihanki}",
            description="下のボタンから商品を購入できます",
            color=discord.Color.blue()
        )
        
        # 商品情報を価格順にソート
        items = []
        for item, info in data.items():
            if isinstance(info, dict) and "price" in info:
                items.append((item, info))
        
        # 価格順に並べ替え
        items.sort(key=lambda x: x[1]["price"])
        
        # 商品を下に表示
        for item, info in items:
            # 在庫状況に応じた絵文字
            if info['stock'] <= 0:
                stock_status = "❌ 在庫切れ"
            elif info['stock'] < 5:
                stock_status = f"⚠️ 残り{info['stock']}個"
            else:
                stock_status = f"✅ 在庫あり ({info['stock']}個)"
                
            # 価格表示
            if info['price'] == 0:
                price_display = "🆓 無料"
            else:
                price_display = f"💰 {info['price']}円"
                
            embed.add_field(
                name=item,
                value=f"{price_display}\n{stock_status}",
                inline=True
            )
            
        embed.set_footer(text=f"最終更新: {discord.utils.utcnow().strftime('%Y/%m/%d %H:%M:%S')}")
        return embed

class SelectJihanki(discord.ui.Select):
    def __init__(self, action):
        self.action = action
        data = load_data()
        options = [discord.SelectOption(label=name, emoji="🏪") for name in data.keys()]
        super().__init__(placeholder="自販機を選んでください", options=options)

    async def callback(self, interaction: discord.Interaction):
        jihanki = self.values[0]
        if self.action == "add_item":
            await interaction.response.send_modal(AddItemModal(jihanki))
        elif self.action == "remove_item":
            await interaction.response.edit_message(view=SelectItem(jihanki, "remove"), content=f"🗑 '{jihanki}' の商品を選んでください")
        elif self.action == "change_stock":
            await interaction.response.edit_message(view=SelectItem(jihanki, "stock"), content=f"📦 '{jihanki}' の商品を選んでください")
        elif self.action == "send_embed":
            await interaction.response.edit_message(view=ChannelSelector(jihanki), content="📤 送信先チャンネルを選んでください")

class ManageView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(self.AddItemButton())
        self.add_item(self.RemoveItemButton())
        self.add_item(self.ChangeStockButton())
        self.add_item(self.SendEmbedButton())
        self.add_item(self.CreateJihankiButton())

    class AddItemButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="🎒 商品追加", style=discord.ButtonStyle.success, row=0)
        async def callback(self, interaction: discord.Interaction):
            view = discord.ui.View()
            view.add_item(SelectJihanki("add_item"))
            await interaction.response.send_message("自販機を選択してください。", view=view, ephemeral=True)

    class RemoveItemButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="🗑 商品削除", style=discord.ButtonStyle.danger, row=1)
        async def callback(self, interaction: discord.Interaction):
            view = discord.ui.View()
            view.add_item(SelectJihanki("remove_item"))
            await interaction.response.send_message("自販機を選択してください。", view=view, ephemeral=True)

    class ChangeStockButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="📦 在庫変更", style=discord.ButtonStyle.secondary, row=1)
        async def callback(self, interaction: discord.Interaction):
            view = discord.ui.View()
            view.add_item(SelectJihanki("change_stock"))
            await interaction.response.send_message("自販機を選択してください。", view=view, ephemeral=True)

    class SendEmbedButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="📤 自販機を送信", style=discord.ButtonStyle.primary, row=2)
        async def callback(self, interaction: discord.Interaction):
            view = discord.ui.View()
            view.add_item(SelectJihanki("send_embed"))
            await interaction.response.send_message("自販機を選択してください。", view=view, ephemeral=True)

    class CreateJihankiButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="➕ 自販機作成", style=discord.ButtonStyle.success, row=2)
        async def callback(self, interaction: discord.Interaction):
            await interaction.response.send_modal(AddJihankiModal())

@bot.tree.command(name="jihanki_manage", description="自販機を管理する")
async def jihanki_manage(interaction: discord.Interaction):
    await interaction.response.send_message("🛠 自販機管理パネル", view=ManageView(), ephemeral=True)

bot.run(TOKEN)
