async def create_vpn_key(user_id):
    try:
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            headers = {"Authorization": f"Bearer {XRAY_API_TOKEN}"}
            
            logger.info(f"📡 Запрос к X-UI API для user_id={user_id}")
            
            # Получаем список инбаундов
            async with session.get(f"{XRAY_API}/list", headers=headers) as resp:
                if resp.status != 200:
                    logger.error(f"❌ Ошибка /list: {resp.status}")
                    return None
                data = await resp.json()
                if not data.get('success'):
                    logger.error(f"❌ X-UI вернул ошибку: {data}")
                    return None
                inbounds = data.get('obj', [])
                if not inbounds:
                    logger.error("❌ Нет входящих подключений")
                    return None
                
                # ===== ЖЁСТКО ФИКСИРУЕМ ID = 1 =====
                TARGET_INBOUND_ID = 1
                inbound = next((x for x in inbounds if x.get('id') == TARGET_INBOUND_ID), None)
                
                if not inbound:
                    logger.error(f"❌ Инбаунд с ID={TARGET_INBOUND_ID} не найден!")
                    return None
                
                inbound_id = inbound.get('id')  # Будет 1
                inbound_port = inbound.get('port')
                inbound_protocol = inbound.get('protocol')
                inbound_remark = inbound.get('remark', 'VPN')
                
                stream_settings = inbound.get('streamSettings', {})
                security = stream_settings.get('security', 'none')
                network = stream_settings.get('network', 'tcp')
                
                sni = "www.microsoft.com"
                if security == "reality":
                    reality_settings = stream_settings.get('realitySettings', {})
                    sni = reality_settings.get('serverNames', ['www.microsoft.com'])[0] if reality_settings.get('serverNames') else "www.microsoft.com"
                
                logger.info(f"✅ Используем inbound: id={inbound_id}, port={inbound_port}")
            
            # Создаём клиента
            client_uuid = str(uuid.uuid4())
            email = f"user_{user_id}_{int(datetime.now().timestamp())}@vpn.com"
            
            # ===== ПРАВИЛЬНЫЙ ЗАПРОС =====
            client_data = {
                "id": inbound_id,  # ← ОБЯЗАТЕЛЬНО 1
                "settings": json.dumps({
                    "clients": [{
                        "id": client_uuid,
                        "email": email,
                        "limitIp": 2,
                        "totalGB": 0,
                        "expiryTime": 0,
                        "enable": True
                    }]
                })
            }
            
            logger.info(f"📤 Создаём клиента: email={email}, inbound_id={inbound_id}")
            
            # ===== ИСПОЛЬЗУЕМ /addClient =====
            async with session.post(f"{XRAY_API}/addClient", headers=headers, json=client_data) as resp:
                if resp.status != 200:
                    logger.error(f"❌ Ошибка /addClient: {resp.status}")
                    return None
                result = await resp.json()
                logger.info(f"📄 Ответ: {json.dumps(result, indent=2)}")
                
                if not result.get('success'):
                    logger.error(f"❌ X-UI не создал клиента: {result}")
                    return None
            
            # Формируем ссылку
            link = f"vless://{client_uuid}@{SERVER_IP}:{inbound_port}?security={security}&encryption=none&type={network}&flow=xtls-rprx-vision&sni={sni}#{inbound_remark}"
            
            db.save_vpn_link(user_id, link)
            logger.info(f"✅ VPN-ссылка создана для user_id={user_id}")
            return link
                
    except Exception as e:
        logger.error(f"❌ Исключение: {e}")
        return None
