import mysql.connector


def get_connection():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",
        database="smart_member_system"
    )
    return conn