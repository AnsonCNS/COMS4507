# -*- coding: utf-8 -*-
"""Timeseries Cryptobot Integration .ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1P0m45z9OgfVFNNeZPtZ3DCyCQbRnBD4V
"""

import os
import uuid
import numpy as np
import random
import requests
import time
import pandas as pd
from enum import Enum
from prophet import Prophet
from datetime import date, timedelta

# Constants
INITIAL_BALANCE = 1000000  # $1 million
INTERVALS = 5  # seconds
MINIMUM_GROWTH = 0.02  # minimum 2% increase in predicted price to trigger buy
STOP_LOSS_PERCENTAGE = 0.05  # limit loss to 5%
GOAL = 1200000 # $1.2 million

""" Time Series Prediction Functions """


def preprocess_data(data_url):
    df = pd.read_csv(data_url)
    df = df.drop(['Adj Close'], axis=1)
    df.rename(columns={'Date': 'ds', 'Close': 'y'}, inplace=True)
    return df


def train_prophet_model(df_train):
    m = Prophet(interval_width=0.95, n_changepoints=7)
    m.fit(df_train)
    return m


def predict_with_prophet(model, future_dates):
    forecast = model.predict(future_dates)
    return forecast


def prepare_prophet_input_data(model, days_to_predict=1):
    future = model.make_future_dataframe(periods=days_to_predict)
    return future


def predict_future_price(model, days_to_predict=60):
    input_data = prepare_prophet_input_data(model, days_to_predict)
    predicted_price = predict_with_prophet(model, input_data)
    # gets the predicted price for tomorrow
    tmr = str(date.today() + timedelta(days=1))
    return predicted_price.loc[predicted_price['ds'] == tmr, 'yhat'].values[0]

class BitcoinTransaction:
    def __init__(self, transaction_type, price, amount, volume, profit_or_loss=None, transaction_trigger=None):
        self.transaction_type = transaction_type
        self.price = price
        self.amount = amount
        self.volume = volume
        self.profit_or_loss = profit_or_loss
        self.transaction_trigger = transaction_trigger
        self.transaction_id = uuid.uuid4()

    def __str__(self):

    def __repr__(self):
        return f"({str(self)})"


class TransactionTypes(Enum):
    BUY = 1
    SELL = 2


""" Trading Bot Functions """


def get_price():
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {"X-CMC_PRO_API_KEY": "91d6c06b-2f3c-458e-98b2-3e0de816e413"}
    params = {"symbol": "BTC"}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        return data["data"]["BTC"]["quote"]["USD"]["price"]
    else:
        return None


def take_decision(current_price, predicted_price, balance, buy_order, sell_order):
    # no buy orders placed yet
    if buy_order is None:
        # Check if price is predicted to grow beyond minimum required growth
        if predicted_price >= current_price * (1 + MINIMUM_GROWTH):
            # Check if we have sufficient balance
            if balance > 0:
                # Calculate the volume of BTC we can buy with our balance and the dollar amount
                volume = balance / current_price
                amount = balance
                # Place the buy order
                trigger = "Predicted future growth"
                buy_order = BitcoinTransaction(TransactionTypes.BUY, current_price, amount, volume, trigger)
                print("New buy order placed:", buy_order)
                balance -= amount
            else:
                print("Insufficient balance to place a new buy order")
        else:
            print(f"Predicted future price does not meet the minimum growth requirement ({MINIMUM_GROWTH * 100}%) for buy trigger")
    elif sell_order is None:
        # Check if current price has fallen to trigger stoploss sell, minimize loss
        if current_price <= buy_order.price * (1 - STOP_LOSS_PERCENTAGE):
            volume = buy_order.volume
            amount = current_price * volume
            # calculate the loss (negative profit) incurred in this sell order
            profit_or_loss = volume * (current_price - buy_order.price)
            trigger = "Current price triggered stoploss"
            sell_order = BitcoinTransaction(
                TransactionTypes.SELL, current_price, amount, volume, profit_or_loss, trigger)
            print("New sell order placed:", sell_order)
            balance += amount
        # Check if investment goal has been reached
        elif balance + (current_price * buy_order.volume) >= GOAL:
            volume = buy_order.volume
            amount = current_price * volume
            # calculate the profit/loss incurred in this sell order
            profit_or_loss = volume * (current_price - buy_order.price)
            trigger = "Investment goal reached"
            sell_order = BitcoinTransaction(
                TransactionTypes.SELL, current_price, amount, volume, profit_or_loss, trigger)
            print("New sell order placed:", sell_order)
            balance += amount
        # Check if predicted future price will fall below stoploss of current price, prevent possible loss
        elif predicted_price <= current_price * (1 - STOP_LOSS_PERCENTAGE):
            volume = buy_order.volume
            amount = current_price * volume
            # calculate the profit/loss incurred in this sell order
            profit_or_loss = volume * (current_price - buy_order.price)
            trigger = "Predicted future price triggered stoploss"
            sell_order = BitcoinTransaction(
                TransactionTypes.SELL, current_price, amount, volume, profit_or_loss, trigger)
            print("New sell order placed:", sell_order)
            balance += amount
        else:
            print("Waiting for price to reach sell threshold")

    return buy_order, sell_order, balance


# Main program
def main():
    balance = INITIAL_BALANCE
    buy_order = None
    sell_order = None
    goal_reached = False

    # url = 'https://raw.githubusercontent.com/yetanotherpassword/COMS4507/main/BTC-USD.csv'
    # update this url to new dataset for future retraining.
    url = 'https://raw.githubusercontent.com/AnsonCNS/COMS4507/main/BTC-USD_2023-05-07.csv'
    preprocessed_data = preprocess_data(url)
    last_day_index = len(preprocessed_data.index)
    # split dataset into 85% training (311/365 days), 15% testing (54/365 days)
    df_train = preprocessed_data.head(last_day_index - 54)

    model = train_prophet_model(df_train)
    transaction_record = []
    profit_and_loss_record = []

    #FIXME the line below is for experimental demonstration, remove line to get real prices
    price = get_price()

    # keep running the bot if there is positive balance or an existing buy order has been placed.
    while (balance > 0 or buy_order) and not goal_reached:
        # FIXME
        # uncomment the following line to get real prices
        # current_price = get_price()

        # FIXME
        # the following line is for experimental demonstration, remove line to get real prices
        current_price = random.randint(int(price*(1-0.1)), int(price*(1+0.1)))

        if current_price is not None:
            print("Current price of BTC: $", current_price)
            predicted_price = predict_future_price(model)
            print("Predicted future price of BTC: $", predicted_price)
            buy_order, sell_order, balance = take_decision(
                current_price, predicted_price, balance, buy_order, sell_order
            )

            if sell_order:
                # record transaction
                transaction_record.append(sell_order)
                print("Sell order fulfilled. Profit: $", sell_order.profit_or_loss)
                profit_and_loss_record.append({sell_order.transaction_id: sell_order.profit_or_loss})

                # reset orders
                buy_order = None
                sell_order = None

            elif buy_order:
                # record transaction
                transaction_record.append(buy_order)
            
            if balance >= GOAL:
                goal_reached = True
                print("Investment goal reached! Stop trading.")
            

            print("Remaining balance (USD): $", balance, "\n")

        else:
            print("Error getting price from CoinMarketCap API")

        time.sleep(INTERVALS)

    print("Transaction record:", transaction_record)
    print("Profit and Loss:", profit_and_loss_record)


if __name__ == '__main__':
    main()