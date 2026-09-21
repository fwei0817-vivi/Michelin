# A Smarter Way to Order for the Table

Product Management with AI (IEOR E4577) — Week 3 Proposal

## Problem Definition

When three to six people are dining together in a Chinese restaurant or a Korean restaurant,
someone has to decide what to order. They need enough food for everyone to eat, the dishes
should be well-matched, and the dietary restrictions and budgets of each person should be
taken into account. The menu often doesn't make it easy for people to make choices: just by
the names of the dishes, it may not be possible to know what the food contains or how many
portions to order. Even for a casual dinner with friends, it can turn into a long discussion
about ordering.

## User(s)

Li is a graduate student. On Friday night, she and five classmates had dinner at a Korean
restaurant. Each of them wanted to spend about 25 dollars. She was ordering food for the
table. One of the classmates was a vegetarian and another was allergic to shellfish. But she
didn't have a good command of Korean, so she couldn't determine what dishes they could have.
The waiter came to inquire about the order, while she was still trying to figure out what
could be prepared for the six people within the budget.

## Initial Idea

**Trigger condition:** The user selects the menu, enters the number of diners, the budget,
and the dietary restrictions for each person.

**Model steps:** The OCR reads the dish names, and then the large language model classifies
and organizes each dish based on the main ingredients, cooking methods, and whether it
contains meat or is vegetarian. An independent algorithm first checks the dietary
restrictions, and then generates a dining plan that meets the budget and portion
requirements. The system will rate the order based on the variety of dish types and
nutritional balance.

**Output result:** The application displays the recommended dining suggestions in card form,
along with a brief description of the selection of each dish. It will also indicate whether
the order meets the group requirements.

**Next step operation:** The user can confirm the order or change individual dishes. If no
combination can meet all the requirements, the application will clearly point out the
conflicts instead of quietly giving up a certain requirement.

## Initial Technical Plan

**Tools:** We will use a multimodal model or OCR technology to read the menu, and then use a
LLM to organize the information of each dish. An independent rule engine will combine the
dishes according to the user's requirements to form an order. The application will display
the recommended order in card form.

**Data:** We will use the menu photos of Chinese restaurants available online, as well as the
photos we took ourselves, to test this application. The user inputs the number of people,
the budget and dietary restrictions. For now, we do not need to provide the data of previous
orders.

**What we will not build:** The first version only supports the Chinese menu. Users may still
need to place orders and make payments at the restaurant themselves. The system will not use
past orders to provide personalized recommendations.

## Success Criteria

We will test the application by simulating group purchase orders. Our goal is to meet
everyone's dietary needs and keep the cost within 5% of the budget. It is suggested that the
dishes may not suit everyone's taste at first. Users can view the recommended order before
confirming and make modifications to the dishes.

---

See `decisions.md` for the revisions agreed after the Week 3 review.
