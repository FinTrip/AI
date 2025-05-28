@csrf_exempt
@require_POST
def save_schedule(request):
    db = None
    cursor = None
    try:
        # **Parse JSON từ request**
        data = json.loads(request.body)
        user_id = data.get("user_id")
        if not user_id:
            logger.error("Thiếu user_id trong request")
            return JsonResponse({"error": "Thiếu user_id"}, status=400)

        # **Kết nối database**
        db = MySQLdb.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            passwd=MYSQL_PASSWORD,
            db=MYSQL_DB,
            port=MYSQL_PORT,
            charset=MYSQL_CHARSET
        )
        cursor = db.cursor()
        logger.info(f"Kết nối database thành công cho user_id: {user_id}")

        # **Kiểm tra user_id có tồn tại không**
        cursor.execute("SELECT id FROM users WHERE id = %s", [user_id])
        if not cursor.fetchone():
            logger.error(f"Không tìm thấy user với id: {user_id}")
            return JsonResponse({"error": "Không tìm thấy người dùng"}, status=404)

        # **Lấy dữ liệu từ request**
        schedule_name = data.get("schedule_name", "Lịch trình của tôi").strip()
        days_data = data.get("days", [])
        hotel_data = data.get("hotel", {})

        if not days_data or not isinstance(days_data, list):
            logger.error("Danh sách ngày rỗng hoặc không hợp lệ")
            return JsonResponse({"error": "Danh sách ngày rỗng hoặc không hợp lệ"}, status=400)

        # **Chèn dữ liệu vào bảng schedules**
        now = datetime.now()
        cursor.execute("INSERT INTO schedules (user_id, name, created_at) VALUES (%s, %s, %s)",
                       [user_id, schedule_name, now])
        schedule_id = cursor.lastrowid
        logger.info(f"Đã chèn schedule với id: {schedule_id}")

        # **Chèn dữ liệu vào bảng hotels**
        if hotel_data and isinstance(hotel_data, dict):
            name = hotel_data.get("name", "").strip()
            if name:
                # Xử lý price
                price_str = hotel_data.get("price", "")
                price = None
                if price_str:
                    try:
                        price = float(price_str.replace(",", ""))
                    except ValueError:
                        logger.warning(f"Price không hợp lệ: {price_str}")

                # Xử lý location_rating
                location_rating_str = hotel_data.get("location_rating", "")
                location_rating = None
                if location_rating_str:
                    try:
                        location_rating = float(location_rating_str)
                    except ValueError:
                        logger.warning(f"Location_rating không hợp lệ: {location_rating_str}")
                else:
                    location_rating = 3

                # Xử lý hotel_class
                hotel_class_raw = hotel_data.get("hotel_class")
                hotel_class = extract_hotel_class(hotel_class_raw) if hotel_class_raw else None

                # Chèn dữ liệu với đúng 9 tham số
                cursor.execute(
                    """
                    INSERT INTO hotels (schedule_id, name, address, description, price, hotel_class,
                                       img_origin, location_rating, link,created_at,updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        schedule_id,
                        name,
                        "",  # Address không có trong hotel_data, dùng chuỗi rỗng
                        hotel_data.get("description", ""),
                        price,
                        hotel_class,
                        hotel_data.get("img_origin", ""),
                        location_rating,
                        hotel_data.get("link", ""),
                        now,now
                    ]
                )
                logger.info(f"Đã chèn hotel cho schedule_id: {schedule_id}")
            else:
                logger.warning("Thiếu tên khách sạn, không chèn hotel")

        # **Chèn dữ liệu vào bảng days và itineraries**
        for day in days_data:
            date_str = day.get("date_str", "").strip()
            if not date_str:
                date_str = datetime.now().strftime("%Y-%m-%d")
                logger.info(f"date_str không được cung cấp, sử dụng ngày hiện tại: {date_str}")
            else:
                try:
                    parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    date_str = parsed_date.strftime("%Y-%m-%d")
                except ValueError:
                    logger.error(f"Định dạng date_str không hợp lệ: {date_str}")
                    return JsonResponse({"error": f"Định dạng date_str không hợp lệ: {date_str}"}, status=400)

            cursor.execute(
                "INSERT INTO days (schedule_id, day_index, date_str) VALUES (%s, %s, %s)",
                [schedule_id, day.get("day_index", 0), date_str]
            )
            day_id = cursor.lastrowid
            logger.info(f"Đã chèn day với id: {day_id}")

            for item in day.get("itinerary", []):
                if not isinstance(item, dict):
                    logger.warning(f"Item không phải dict: {item}")
                    continue
                food_title = item.get("food_title", "").strip()
                place_title = item.get("place_title", "").strip()
                if not food_title and not place_title:
                    logger.info("Bỏ qua item vì thiếu cả food_title và place_title")
                    continue

                food_rating = item.get("food_rating")
                if food_rating:
                    try:
                        food_rating = float(food_rating)
                    except (ValueError, TypeError):
                        food_rating = None

                place_rating = item.get("place_rating")
                if place_rating:
                    try:
                        place_rating = float(place_rating)
                    except (ValueError, TypeError):
                        place_rating = None

                cursor.execute(
                    """
                    INSERT INTO itineraries (
                        day_id, timeslot, food_title, food_rating, food_price, food_address,
                        food_phone, food_link, food_image, food_time, place_title, place_rating,
                        place_description, place_address, place_img, place_link, place_time,
                        `order`, schedule_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        day_id,
                        item.get("timeslot", "")[:20],
                        food_title[:100],
                        food_rating,
                        str(item.get("food_price", ""))[:50],
                        item.get("food_address", "")[:200],
                        item.get("food_phone", "")[:20],
                        item.get("food_link", "")[:255],
                        item.get("food_image", "")[:255],
                        item.get("food_time", "")[:255] if item.get("food_time") else None,
                        place_title[:100],
                        place_rating,
                        item.get("place_description", ""),
                        item.get("place_address", "")[:200],
                        item.get("place_img", "")[:255],
                        item.get("place_link", "")[:255],
                        item.get("place_time", "")[:255] if item.get("place_time") else None,
                        item.get("order", 0),
                        schedule_id
                    ]
                )
                logger.info(f"Đã chèn itinerary cho day_id: {day_id}")

        # **Chèn dữ liệu vào bảng sharedlinks**
        share_token = str(uuid.uuid4()).lower()
        share_link = f"{request.scheme}://{request.get_host()}/recommend/view-schedule/{share_token}/"
        cursor.execute(
            "INSERT INTO sharedlinks (schedule_id, share_link, created_at) VALUES (%s, %s, NOW())",
            [schedule_id, share_link]
        )
        logger.info(f"Đã chèn sharedlink cho schedule_id: {schedule_id}")

        # **Commit tất cả thay đổi**
        db.commit()
        logger.info("Đã commit tất cả thay đổi thành công")

        return JsonResponse({
            "message": "Lịch trình lưu thành công",
            "schedule_id": schedule_id,
            "share_link": share_link
        }, status=201)

    except json.JSONDecodeError:
        logger.error("JSON không hợp lệ trong request")
        return JsonResponse({"error": "JSON không hợp lệ"}, status=400)
    except MySQLdb.Error as e:
        if db:
            db.rollback()
        logger.error(f"Lỗi database: {str(e)}")
        traceback.print_exc()
        return JsonResponse({"error": "Lỗi cơ sở dữ liệu"}, status=500)
    except Exception as e:
        if db:
            db.rollback()
        logger.error(f"Lỗi không xác định: {str(e)}")
        traceback.print_exc()
        return JsonResponse({"error": "Lỗi server"}, status=500)
    finally:
        if cursor:
            cursor.close()
        if db and db.open:
            db.close()
            logger.info("Đã đóng kết nối database")


@csrf_exempt
@require_POST
def recommend_travel_schedule(request):
    try:
        data = json.loads(request.body)

        user_id = data.get("user_id")
        if not user_id:
            logger.error("Thiếu user_id trong request")
            return JsonResponse({"error": "Thiếu user_id"}, status=400)

        # Chuyển user_id thành số nguyên (đảm bảo định dạng đúng)
        try:
            user_id = int(user_id)
        except ValueError:
            logger.error("user_id phải là số nguyên")
            return JsonResponse({"error": "user_id phải là số nguyên"}, status=400)

        cache_key_prefix = request.session.session_key
        province = data.get('province', cache.get(f'selected_province_{cache_key_prefix}', ''))
        start_day = data.get('start_day', cache.get(f'start_day_{cache_key_prefix}', ''))
        end_day = data.get('end_day', cache.get(f'end_day_{cache_key_prefix}', ''))
        flight_info = data.get('flight_info', None)
        hotel_info = data.get('hotel_info', None)

        if not province or not start_day or not end_day:
            logger.error("Missing required fields in travel_schedule")
            return JsonResponse({"error": "Thiếu thông tin tỉnh, ngày đi hoặc ngày về"}, status=400)

        db = None
        cursor = None
        try:
            db = MySQLdb.connect(
                host=MYSQL_HOST,
                user=MYSQL_USER,
                passwd=MYSQL_PASSWORD,
                db=MYSQL_DB,
                port=MYSQL_PORT,
                charset=MYSQL_CHARSET
            )
            cursor = db.cursor()
            logger.info(f"Kết nối database thành công cho user_id: {user_id}")

            # Kiểm tra user_id có tồn tại không và lấy wallet_balance
            cursor.execute("SELECT id, wallet_balance FROM users WHERE id = %s", [user_id])
            user_data = cursor.fetchone()
            if not user_data:
                logger.error(f"Không tìm thấy user với id: {user_id}")
                return JsonResponse({"error": "Không tìm thấy người dùng"}, status=404)

            # Kiểm tra và trừ wallet_balance
            wallet_balance = user_data[1]
            if wallet_balance < 1000:
                logger.error(f"Số dư không đủ cho user_id: {user_id}")
                return JsonResponse({"error": "Số dư không đủ"}, status=400)

            new_balance = wallet_balance - 1000
            cursor.execute("UPDATE users SET wallet_balance = %s WHERE id = %s", [new_balance, user_id])
            db.commit()
            logger.info(f"Đã trừ 1000 từ wallet_balance cho user_id: {user_id}")

        except MySQLdb.Error as e:
            logger.error(f"Lỗi cơ sở dữ liệu: {str(e)}")
            if db:
                db.rollback()
            return JsonResponse({"error": "Lỗi cơ sở dữ liệu"}, status=500)

        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

        if flight_info:
            cache.set(f'selected_flight_{cache_key_prefix}', flight_info, timeout=3600)
            logger.info(f"Flight info updated in cache: {flight_info}")
        if hotel_info:
            cache.set(f'selected_hotel_{cache_key_prefix}', hotel_info, timeout=3600)
            logger.info(f"Hotel info updated in cache: {hotel_info}")

        selected_hotel = cache.get(f'selected_hotel_{cache_key_prefix}', {})
        selected_flight = cache.get(f'selected_flight_{cache_key_prefix}', {})

        if not selected_flight:
            logger.warning("No flight information found in cache")
        if not selected_hotel:
            logger.warning("No hotel information found in cache")

        start_date = datetime.strptime(start_day, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_day, "%Y-%m-%d").date()
        current_date = datetime.now().date()
        error_response = check_date_logic(start_date, end_date, current_date)
        if error_response:
            return error_response

        food_df, place_df, _ = load_data(FOOD_FILE, PLACE_FILE)
        schedule_result = recommend_schedule(start_day, end_day, province, food_df, place_df)
        if "error" in schedule_result:
            return JsonResponse({"error": schedule_result["error"]}, status=400)

        response_data = {
            "schedule": schedule_result,
            "hotel": selected_hotel,
            "flight": selected_flight,
            "province": province,
            "timestamp": datetime.now().isoformat(),
            "csrf_token": get_token(request),
        }

        logger.info("Travel schedule generated successfully")
        return JsonResponse(response_data, status=200)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in travel_schedule")
        return JsonResponse({"error": "Dữ liệu JSON không hợp lệ"}, status=400)
    except Exception as e:
        logger.error(f"Error in travel_schedule: {str(e)}")
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)

